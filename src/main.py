import asyncio
import argparse
from dotenv import load_dotenv
from src.graph import graph

load_dotenv()

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pdf", required=True)
    args = parser.parse_args()

    inputs = {"repo_url": args.repo, "pdf_path": args.pdf, "evidences": {}}
    async for event in graph.astream(inputs):
        print(event)

if __name__ == "__main__":
    asyncio.run(main())