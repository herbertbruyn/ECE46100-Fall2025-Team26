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

