import pandas as pd

column_mapping = {
    "feature_id": "ID",
    "module": "Component",
    "requirement": "Description",
    "requirement_type": "Requirement Category"
}

def load_requirements(file_path, column_mapping):
    df = pd.read_excel(file_path)

    requirements = []

    for _, row in df.iterrows():
        req = {}

        for field, column in column_mapping.items():
            value = row.get(column, "")
            if pd.isna(value):
                req[field] = ""
            else:
                req[field] = str(value).strip()

        requirements.append(req)

    return requirements

requirements = load_requirements("data/BL5_req.xlsx", column_mapping)

# test only first 3
requirements = requirements[:3]