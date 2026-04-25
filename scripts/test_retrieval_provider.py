import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import asyncio

from services.reporting_v2.searxng_provider import SearxngRetrievalProvider


async def main() -> None:
    provider = SearxngRetrievalProvider(
        base_url="http://localhost:8088",
        max_results=5,
        fetch_pages=False,
    )

    result = await provider.retrieve(
        {
            "kind": "post",
            "post_text": "Совет Республики Беларуси одобрил законопроект с изменениями в КоАП о пропаганде ЛГБТ чайлдфри и педофилии.",
            "comments": [],
            "decision_inputs": {},
        }
    )

    print(result)


if __name__ == "__main__":
    asyncio.run(main())