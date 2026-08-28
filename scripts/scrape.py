import json
import sys
from datetime import datetime, timedelta

import pandas as pd
from district_helper import assign_districts, load_data
from sodapy import Socrata

try:
    client = Socrata("data.cityofnewyork.us", None)

    today = datetime.now().strftime("%Y-%m-%d")

    # The NYC crash dataset lags real time (often by weeks or months), so a
    # window anchored to "today" can come back empty. Anchor the 7-day window to
    # the most recent crash_date actually present in the dataset instead.
    max_date_result = client.get(
        "h9gi-nx95", select="max(crash_date) as max_crash_date", limit=1
    )
    if not max_date_result or not max_date_result[0].get("max_crash_date"):
        print("Error: Could not determine latest crash_date in dataset!")
        sys.exit(1)

    latest_crash_date = datetime.strptime(
        max_date_result[0]["max_crash_date"][:10], "%Y-%m-%d"
    )
    window_start = (latest_crash_date - timedelta(days=7)).strftime("%Y-%m-%d")
    query = f"SELECT * WHERE crash_date >= '{window_start}' ORDER BY crash_date DESC LIMIT 1000"

    results = client.get("h9gi-nx95", query=query)

    if not results:
        print("Error: No data retrieved!")
        sys.exit(1)

    df = pd.DataFrame.from_records(results)

    if "location" in df.columns:
        df["location"] = df["location"].apply(
            lambda x: json.dumps(x) if isinstance(x, dict) else x
        )

    print(f"Retrieved {len(df)} records")
    print(f"Date range: {df['crash_date'].min()} to {df['crash_date'].max()}")
    print(f"Boroughs represented: {df['borough'].unique().tolist()}")

    output_file = "./data/latest_collisions.csv"
    df.to_csv(output_file, index=False)
    print(f"Data saved to {output_file}")

    # Assign districts using district_helper
    collision_file = "./data/latest_collisions.csv"
    boundary_file = "./data/city_council_boundaries.csv"

    try:
        collisions_gdf, boundaries_gdf = load_data(collision_file, boundary_file)
        merged_gdf = assign_districts(collisions_gdf, boundaries_gdf)

        # Drop unwanted columns before saving
        columns_to_drop = [
            "geometry",
            "index_right",
            "the_geom",
            "Shape_Leng",
            "Shape_Area",
        ]
        # Save the updated CSV with district information
        merged_gdf.drop(columns=columns_to_drop, errors="ignore").to_csv(
            output_file, index=False
        )
        print(f"Updated data saved with districts to {output_file}")
    except Exception as district_error:
        print(f"Error assigning districts: {str(district_error)}")

    summary = {
        "record_count": len(df),
        "date_range": {
            "earliest": df["crash_date"].min(),
            "latest": df["crash_date"].max(),
        },
        "total_injured": int(pd.to_numeric(df.get("number_of_persons_injured", pd.Series(dtype=float)), errors="coerce").sum()),
        "total_killed": int(pd.to_numeric(df.get("number_of_persons_killed", pd.Series(dtype=float)), errors="coerce").sum()),
        "boroughs": df["borough"].value_counts().to_dict(),
    }

    with open(f"summary_{today}.json", "w") as f:
        json.dump(summary, f, indent=2)

except Exception as e:
    print(f"Error occurred: {str(e)}")
    sys.exit(1)
