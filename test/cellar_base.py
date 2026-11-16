import sys
from pathlib import Path

from urllib.request import urlopen
from urllib.error import HTTPError

workspace_root = Path(__file__).parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from src.eurlex.cellar_api import CellarPS, CellarResourceId, CellarAPI
from src.eurlex.constants import MimeType


DOCUMENTS = {
    "Cybersecurity-Act": "35e93bb4-8905-11e9-9369-01aa75ed71a1",
    "NIS2": "9b84d482-85bd-11ed-9887-01aa75ed71a1",
    "DORA": "0caf473a-85bd-11ed-9887-01aa75ed71a1",
    "CER-Directive": "c4d36f49-85bc-11ed-9887-01aa75ed71a1",
    "Cyber-Resilience-Act": "21b7d4eb-a6e2-11ef-85f0-01aa75ed71a1",
    "eIDAS-1": "23b61856-2e82-11e4-8c3c-01aa75ed71a1",
    "eIDAS-2": "459993a1-068e-11ef-a251-01aa75ed71a1",
    "NIS1": "d2912aca-4d75-11e6-89bd-01aa75ed71a1",
    "ENISA-Reg-526-2013": "a227aef3-d802-11e2-bfa7-01aa75ed71a1",
    "DORA-Amending-Directive": "e2e67364-85bd-11ed-9887-01aa75ed71a1",
    "EU-Cybersecurity-Competence-Centre-Regulation": "1f335a13-c82b-11eb-a925-01aa75ed71a1",
    "GDPR": "3e485e15-11bd-11e6-ba9a-01aa75ed71a1",
    "Data-Governance-Act": "b3c148c3-e2d6-11ec-a534-01aa75ed71a1",
    "AI-Act": "dc8116a1-3fe6-11ef-865a-01aa75ed71a1"
}


def get_metadata():
    try:
        resource_ids = {name: CellarResourceId(CellarPS.CELLAR, work_id) for name, work_id in DOCUMENTS.items()}
    except ValueError as e:
        print(e)
        return

    for name, resource_id in resource_ids.items():
        try:
            req = CellarAPI.metadata_request(resource_id)
            with urlopen(req) as response:
                metadata = response.read()
            with open(f"tmp/{name}.rdf", "w", encoding="utf-8") as f:
                f.write(metadata.decode("utf-8"))
        except HTTPError as e:
            print(f"Failed to fetch metadata for {name}: {e}")
        except Exception as e:
            print(f"An error occurred for {name}: {e}")


if __name__ == "__main__":
    get_metadata()