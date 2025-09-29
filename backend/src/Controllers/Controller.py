from typing import List, Optional

from Models.Model import Model
from Models.Manager_Models_Model import ModelManager


class Controller:
    def __init__(self):
        self.model_manager = ModelManager()

    def fetch(self, main_link: str,
              dataset_links: Optional[List[str]] = None,
              code_link: Optional[str] = None) -> Optional[Model]:

        return self.model_manager.where(
            main_link, dataset_links, code_link
        )


if __name__ == "__main__":
    fetcher = Controller()
    dataset_links = [
        "https://huggingface.co/datasets/xlangai/AgentNet",
        "https://huggingface.co/datasets/osunlp/UGround-V1-Data",
        "https://huggingface.co/datasets/xlangai/aguvis-stage2"
    ]
    code_link = "https://github.com/xlang-ai/OpenCUA"
    model_link = "https://huggingface.co/xlangai/OpenCUA-32B"

    model_data = fetcher.fetch(
        model_link,
        dataset_links=dataset_links,
        code_link=code_link
    )
