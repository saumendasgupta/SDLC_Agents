from ingestion.excel_parser import load_requirements
from runner.batch_runner import run_batch
from runner.export import export_results, export_markdown_report

def main():

    print("🚀 Starting SDLC Agent System...")

    # 👇 User-defined mapping (IMPORTANT)
    column_mapping = {
        "feature_id": "ID",
        "module": "Component",
        "requirement": "Description",
        "requirement_type": "Requirement Category"
    }

    # 👇 Step 1: Load Excel
    requirements = load_requirements("data/req.xlsx", column_mapping)

    print(f"Loaded {len(requirements)} requirements")

    # 👇 Step 2: Target requirements for focused QA validation
    target_ids = {"123456", "789123"}
    requirements = [req for req in requirements if str(req.get("feature_id", "")).strip() in target_ids]
    print(f"Selected {len(requirements)} targeted requirements: {sorted(target_ids)}")

    # 👇 Step 3: Run agent
    results = run_batch(requirements)

    # 👇 Step 4: Export
    export_results(results)
    export_markdown_report(results)

    print("✅ Done!")

if __name__ == "__main__":
    main()
