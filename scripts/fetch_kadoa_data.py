from generate_data import DATA_DIR, build_kadoa_disclosures, write_json


def main():
    output_path = DATA_DIR / "financial_disclosures.json"
    write_json(output_path, build_kadoa_disclosures())
    print("Generated", output_path)


if __name__ == "__main__":
    main()
