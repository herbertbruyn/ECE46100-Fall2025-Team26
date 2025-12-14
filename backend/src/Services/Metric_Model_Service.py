import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from Models import Model
from lib.LLM_Manager import LLMManager
from lib.Metric_Result import MetricResult, MetricType
from Helpers import _parse_iso8601, _months_between


class ModelMetricService:
    def __init__(self) -> None:
        logging.info("[Metric Service] Initializing ModelMetricService...")
        try:
            self.llm_manager = LLMManager()
            logging.info("[Metric Service] LLM Manager initialized successfully")
        except Exception as e:
            logging.error(f"[Metric Service] Failed to initialize LLM Manager: {e}")
            raise

    def EvaluateModel(
        self, model_description: str, dataset_description: str
    ) -> MetricResult:
        return MetricResult(
            metric_type=MetricType.PERFORMANCE_CLAIMS,
            value=0.0,
            details={
                "info": "Model evaluation not yet implemented"
            },
            latency_ms=0,
            error=None
        )

    def EvaluatePerformanceClaims(self, Data: Model) -> MetricResult:
        def _compose_source_text(data: Model) -> str:
            readme = ""
            path = getattr(data, "readme_path", None)
            if path:
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        readme = fh.read()
                except Exception:
                    readme = ""
            card = ""
            card_obj = getattr(data, "card", None)
            if card_obj is not None:
                card = str(card_obj)
            text = (readme + "\n\n" + card).strip()
            if len(text) > 16000:
                text = text[:16000] + "\n\n...[truncated]..."
            return text

        def prepare_llm_prompt(data: Model) -> str:
            assert isinstance(data, Model)
            text = _compose_source_text(data)
            return (
                "You are assessing a model card/README for performance claims. "
                "Be recall-oriented and generous. Consider any reasonable hints: "
                "named benchmarks, numbers (accuracy/F1/BLEU/etc.), tables, or "
                "comparisons to baselines/SoTA/leaderboards.\n\n"
                "Output STRICT JSON ONLY with two fields:\n"
                "{\n"
                '  "score": <float between 0.0 and 1.0>,\n'
                '  "notes": "very brief rationale (<=200 chars)"\n'
                "}\n\n"
                "Scoring guidance (soft, not exact):\n"
                "- 0.00–0.20: No claims or evidence.\n"
                "- 0.21–0.50: Mentions benchmarks OR some metrics/figures.\n"
                "- 0.51–0.80: Clear metrics/tables and some comparison signals.\n"
                "- 0.81–1.00: Strong metrics+tabled results and explicit baselines/"
                "SoTA/leaderboard links.\n"
                "When uncertain, prefer a higher score (recall > precision).\n\n"
                "Answer with JSON only. No prose.\n"
                "=== BEGIN TEXT ===\n"
                f"{text[:8000]}\n"
                "=== END TEXT ===\n"
            )

        def parse_llm_response(response: str) -> Dict[str, Any]:
            try:
                if not response or not response.strip():
                    logging.warning("Empty LLM response received")
                    return {"score": 0.0, "notes": "Empty response from LLM"}
                
                # Strip markdown code block formatting if present
                clean_response = response.strip()
                if clean_response.startswith("```json"):
                    clean_response = clean_response[7:]  # Remove ```json
                if clean_response.startswith("```"):
                    clean_response = clean_response[3:]   # Remove ```
                if clean_response.endswith("```"):
                    clean_response = clean_response[:-3]  # Remove trailing ```
                clean_response = clean_response.strip()
                
                obj = json.loads(clean_response)

                score = obj.get("score", 0.0)

                try:
                    score = float(score)
                except (TypeError, ValueError):
                    score = 0.0

                score = max(0.0, min(1.0, score))

                return {
                    "score": score,
                    "notes": str(obj.get("notes", ""))[:400],
                }
            
            except json.JSONDecodeError as e:
                logging.warning(f"Failed to parse LLM response as JSON: {e}")
                logging.warning(f"Raw response: {response[:200]}...")
                return {
                    "score": 0.0,
                    "notes": f"JSON parse error: {str(e)[:100]}"
        }

        try:
            logging.info("[Performance Claims] Starting evaluation...")
            logging.debug(f"[Performance Claims] Model data attributes: {dir(Data)}")
            
            prompt = prepare_llm_prompt(Data)
            logging.info(f"[Performance Claims] Prepared prompt (length: {len(prompt)})")
            
            logging.info("[Performance Claims] Calling LLM API...")
            response = self.llm_manager.call_genai_api(prompt)
            logging.info(f"[Performance Claims] LLM response received")
            logging.info(f"[Performance Claims] Response content: {repr(response.content[:500])}")
            
            response_text = ""
            if hasattr(response, 'content'):
                response_text = response.content
                logging.debug("[Performance Claims] Extracted content from response.content")
            elif isinstance(response, str):
                response_text = response
                logging.debug("[Performance Claims] Response is a string")
            else:
                response_text = str(response)
                logging.warning("[Performance Claims] Converted response to string")
            
            logging.info("[Performance Claims] Parsing LLM response...")
            parsed = parse_llm_response(response_text)
            logging.info(f"[Performance Claims] Parsed result: {parsed}")

            # Use the score directly from the LLM response
            score = parsed.get("score", 0.0)
            logging.info(f"[Performance Claims] Final score: {score}")

            details = {"mode": "llm", **parsed}

            return MetricResult(
                metric_type=MetricType.PERFORMANCE_CLAIMS,
                value=score,
                details=details,
                latency_ms=0,
            )

        except Exception as exc:
            logging.error(f"[Performance Claims] Evaluation failed with error: {exc}")
            logging.error(f"[Performance Claims] Error type: {type(exc).__name__}")
            import traceback
            logging.error(f"[Performance Claims] Traceback:\n{traceback.format_exc()}")
            raise RuntimeError("LLM evaluation failed") from exc

    def EvaluateBusFactor(self, Data: Model) -> MetricResult:
        def _contributors_score(contrib_count: int) -> float:
            if contrib_count >= 7:
                return 1.0
            if 4 <= contrib_count <= 6:
                return 0.7
            if 2 <= contrib_count <= 3:
                return 0.5
            if contrib_count == 1:
                return 0.3
            return 0.0

        def _recency_score(last_commit: Optional[datetime]) -> float:
            if last_commit is None:
                return 0.0
            now = datetime.now(timezone.utc)
            months = _months_between(now, last_commit)
            if months < 3.0:
                return 1.0
            score = 1.0 - 0.1 * (months - 3.0)
            if months > 12.0:
                return 0.0
            if score < 0.0:
                return 0.0
            if score > 1.0:
                return 1.0
            return score

        def _latest_commit_ts(data: Model) -> Optional[datetime]:
            commits = getattr(data, "repo_commit_history", [])
            for item in commits:
                commit = item.get("commit", {})
                author = commit.get("author", {})
                ts = author.get("date")
                if isinstance(ts, str):
                    dt = _parse_iso8601(ts)
                    if dt is not None:
                        return dt
            return None

        def _contributors_count(data: Model) -> int:
            contribs = getattr(data, "repo_contributors", [])
            if not isinstance(contribs, list):
                return 0
            return sum(
                1 for c in contribs
                if int(c.get("contributions", 0)) > 0
            )

        try:
            n_contrib = _contributors_count(Data)
            last_ts = _latest_commit_ts(Data)

            c_score = _contributors_score(n_contrib)
            r_score = _recency_score(last_ts)

            score = 0.7 * c_score + 0.3 * r_score
            if score < 0.0:
                score = 0.0
            if score > 1.0:
                score = 1.0

            months = None
            if last_ts is not None:
                months = round(
                    _months_between(datetime.now(timezone.utc), last_ts), 2)

            details = {
                "contributors_count": n_contrib,
                "contributors_score": round(c_score, 3),
                "last_commit_months_ago": months,
                "recency_score": round(r_score, 3),
                "blend": "0.7*contributors + 0.3*recency",
            }

            return MetricResult(
                metric_type=MetricType.BUS_FACTOR,
                value=score,
                details=details,
                latency_ms=0,
            )

        except Exception as e:
            logging.error(f"Failed to evaluate bus factor: {e}")
            raise RuntimeError("Bus factor evaluation failed") from e

    def EvaluateSize(self, Data: Model) -> MetricResult:
        def _size_metric(x: float) -> float:
            return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x

        def _size_band_mb(
            x: float, a: float, b: float, c: float, d: float
        ) -> float:
            if x <= a:
                return 1.0
            if x <= b:
                return 0.6
            if x <= c:
                return 0.3
            if x <= d:
                return 0.1
            return 0.0

        try:
            if isinstance(Data.repo_metadata, dict):
                s = (
                    Data.repo_metadata.get("size_mb")
                    or Data.repo_metadata.get("size")
                )

                size_mb = 0.0
                if isinstance(s, str):
                    if s.lower().endswith("gb"):
                        try:
                            size_mb = float(s[:-2]) * 1024.0
                        except (ValueError, TypeError) as e:
                            logging.error(
                                f"Failed to parse GB size '{s}': {e}"
                            )
                            raise ValueError(
                                f"Invalid GB size format: {s}"
                            ) from e
                    else:
                        try:
                            size_mb = float(s)
                        except (ValueError, TypeError) as e:
                            logging.error(
                                f"Failed to parse MB size '{s}': {e}"
                            )
                            raise ValueError(
                                f"Invalid MB size format: {s}"
                            ) from e
                elif isinstance(s, (int, float)):
                    size_mb = float(s)

                r_pi = _size_metric(
                    _size_band_mb(size_mb, 200, 500, 1500, 2000)
                )

                j_nano = _size_metric(
                    _size_band_mb(size_mb, 400, 1500, 4000, 6000)
                )

                d_pc = _size_metric(
                    _size_band_mb(size_mb, 2000, 7000, 20000, 40000)
                )

                aws = _size_metric(
                    _size_band_mb(size_mb, 40000, 60000, 120000, 240000)
                )

                sizeScore = (r_pi + j_nano + d_pc + aws) / 4.0

                return MetricResult(
                    metric_type=MetricType.SIZE_SCORE,
                    value=sizeScore,
                    details={"derived_size_mb": size_mb},
                    latency_ms=0,
                )
            else:
                logging.warning("Model repo_metadata is not a dictionary")
                return MetricResult(
                    metric_type=MetricType.SIZE_SCORE,
                    value=0.0,
                    details={"error": "repo_metadata is not a dictionary"},
                    latency_ms=0,
                )

        except Exception as e:
            logging.error(f"Failed to evaluate model size: {e}")
            raise RuntimeError("Size evaluation failed") from e

    def EvaluateDatasetAndCodeAvailabilityScore(self,
                                                Data: Model) -> MetricResult:
        """
        Evaluate dataset and code availability using regex patterns (NO LLM)
        Scoring:
        - lists_training_datasets: 0.3 points
        - links_to_huggingface_datasets: 0.3 points
        - links_to_code_repo: 0.4 points
        """
        import re

        def _get_readme_content(data: Model) -> str:
            readme = ""
            path = getattr(data, "readme_path", None)
            if path:
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        readme = fh.read()
                except Exception:
                    readme = ""
            return readme

        try:
            logging.info("[Availability] Starting regex-based dataset/code availability evaluation...")

            readme = _get_readme_content(Data)
            card_str = str(getattr(Data, "card", ""))
            text = (readme + "\n\n" + card_str).strip()

            # Check for dataset mentions (common dataset names or patterns)
            dataset_patterns = [
                r'(?:dataset|training[_ ]?data|trained[_ ]?on|fine[- ]?tuned[_ ]?on)[:\s]+([a-zA-Z0-9/_-]+)',
                r'\b(?:ImageNet|COCO|MNIST|CIFAR|SQuAD|GLUE|SuperGLUE|WikiText|Penn Treebank)\b',
                r'huggingface\.co/datasets/([a-zA-Z0-9/_-]+)',
            ]
            lists_training_datasets = any(re.search(p, text, re.IGNORECASE) for p in dataset_patterns)

            # Check for HuggingFace dataset URLs
            hf_dataset_pattern = r'huggingface\.co/datasets/([a-zA-Z0-9/_-]+)'
            links_to_huggingface_datasets = bool(re.search(hf_dataset_pattern, text, re.IGNORECASE))

            # Check for code repository links (GitHub, GitLab, etc.)
            code_patterns = [
                r'github\.com/([a-zA-Z0-9/_-]+)',
                r'gitlab\.com/([a-zA-Z0-9/_-]+)',
                r'(?:code|repository|repo)[:\s]+https?://[^\s]+',
            ]
            links_to_code_repo = any(re.search(p, text, re.IGNORECASE) for p in code_patterns)

            # Calculate score
            score = 0.0
            if lists_training_datasets:
                score += 0.3
                logging.info("[Availability] +0.3 for training datasets mention")
            if links_to_huggingface_datasets:
                score += 0.3
                logging.info("[Availability] +0.3 for HuggingFace dataset links")
            if links_to_code_repo:
                score += 0.4
                logging.info("[Availability] +0.4 for code repository links")

            if score > 1.0:
                score = 1.0

            logging.info(f"[Availability] Final score: {score} (regex-based, no LLM)")

            details = {
                "mode": "regex",
                "lists_training_datasets": lists_training_datasets,
                "links_to_huggingface_datasets": links_to_huggingface_datasets,
                "links_to_code_repo": links_to_code_repo,
                "notes": "Regex-based analysis (no LLM required)"
            }

            return MetricResult(
                metric_type=MetricType.DATASET_AND_CODE_SCORE,
                value=score,
                details=details,
                latency_ms=0,
            )

        except Exception as exc:
            logging.error(f"[Availability] Evaluation failed with error: {exc}")
            logging.error(f"[Availability] Error type: {type(exc).__name__}")
            import traceback
            logging.error(f"[Availability] Traceback:\n{traceback.format_exc()}")
            raise RuntimeError("Dataset and code availability "
                               "evaluation failed") from exc

    def EvaluateCodeQuality(self, Data: Model) -> MetricResult:
        def _check_test_files(repo_contents: list) -> bool:
            if not isinstance(repo_contents, list):
                return False

            test_indicators = [
                'test', 'tests', 'testing', 'unittest', 'unit_test',
                'test_', '_test', 'spec', 'specs'
            ]

            for item in repo_contents:
                if isinstance(item, dict):
                    name = item.get('name', '').lower()
                    path = item.get('path', '').lower()

                    for indicator in test_indicators:
                        if (indicator in name or indicator in path or
                                name.startswith('test_') or
                                name.endswith('_test.py') or
                                name.endswith('_test') or
                                'test.py' in name):
                            return True
            return False

        def _check_dependency_management(repo_contents: list) -> bool:
            if not isinstance(repo_contents, list):
                return False

            dependency_files = [
                'requirements.txt', 'setup.py', 'pyproject.toml',
                'pipfile', 'poetry.lock', 'conda.yml', 'environment.yml'
            ]

            for item in repo_contents:
                if isinstance(item, dict):
                    name = item.get('name', '').lower()
                    if name in dependency_files:
                        return True
            return False

        def _check_structure_heuristics(repo_contents: list) -> bool:
            """Check for good structure using heuristics (no LLM)"""
            if not isinstance(repo_contents, list) or len(repo_contents) == 0:
                return False

            # Look for common good structure indicators
            structure_indicators = [
                'src/', 'lib/', 'pkg/', 'internal/',  # Source directories
                'cmd/', 'bin/', 'scripts/',  # Binary/script directories
                'docs/', 'doc/', 'documentation/',  # Documentation
                'examples/', 'samples/',  # Examples
                'config/', 'configs/',  # Configuration
            ]

            found_indicators = 0
            for item in repo_contents:
                if isinstance(item, dict):
                    path = item.get('path', '').lower()
                    for indicator in structure_indicators:
                        if indicator in path:
                            found_indicators += 1
                            break

            # If we have 2+ structure indicators, assume good structure
            return found_indicators >= 2

        def _check_documentation(repo_contents: list) -> bool:
            """Check for documentation files (no LLM)"""
            if not isinstance(repo_contents, list):
                return False

            doc_indicators = ['readme', 'license', 'contributing', 'changelog', 'docs/', 'doc/']

            for item in repo_contents:
                if isinstance(item, dict):
                    name = item.get('name', '').lower()
                    path = item.get('path', '').lower()
                    for indicator in doc_indicators:
                        if indicator in name or indicator in path:
                            return True
            return False

        def _analyze_code_with_llm(repo_contents: list) -> Dict[str, Any]:
            """Analyze code structure - fallback to heuristics if LLM fails"""
            logging.info("[Code Quality] Starting code structure analysis...")

            # Try LLM first, but use heuristics as fallback
            try:
                repo_summary = []
                for item in repo_contents[:50]:
                    if isinstance(item, dict):
                        name = item.get('name', '')
                        item_type = item.get('type', '')
                        repo_summary.append(f"{item_type}: {name}")

                repo_text = "\n".join(repo_summary)

                if len(repo_summary) == 0:
                    raise ValueError("Empty repository contents")

                prompt = (
                    "CRITICAL: You MUST respond with ONLY valid JSON. "
                    "No explanations, no markdown, no code blocks.\n\n"
                    "Task: Analyze this repository structure for code quality. "
                    "Return EXACTLY this JSON structure:\n\n"
                    "{\n"
                    '  "has_comprehensive_tests": true|false,\n'
                    '  "shows_good_structure": true|false,\n'
                    '  "has_documentation": true|false,\n'
                    '  "notes": "analysis summary"\n'
                    "}\n\n"
                    "Rules:\n"
                    "1. ONLY return JSON - nothing else\n"
                    "2. Use true/false (lowercase) for booleans\n"
                    "3. Keep notes under 30 characters\n\n"
                    "Evaluation criteria:\n"
                    "- has_comprehensive_tests: Are there test files covering "
                    "multiple components?\n"
                    "- shows_good_structure: Well-organized directories and "
                    "separation of concerns?\n"
                    "- has_documentation: README, docs, or documentation "
                    "files present?\n\n"
                    "Repository structure:\n"
                    f"{repo_text}\n\n"
                    "Remember: ONLY return the JSON object."
                )

                logging.info(f"[Code Quality] Calling LLM API...")
                response = self.llm_manager.call_genai_api(prompt)
                logging.info(f"[Code Quality] LLM response received")

                obj = json.loads(response.content)

                result = {
                    "has_comprehensive_tests": bool(obj.get("has_comprehensive_tests", False)),
                    "shows_good_structure": bool(obj.get("shows_good_structure", False)),
                    "has_documentation": bool(obj.get("has_documentation", False)),
                    "notes": str(obj.get("notes", ""))[:400],
                }
                logging.info(f"[Code Quality] LLM analysis successful: {result}")
                return result

            except Exception as e:
                logging.warning(f"[Code Quality] LLM analysis failed, using heuristics: {e}")

                # Fallback to heuristics
                has_structure = _check_structure_heuristics(repo_contents)
                has_docs = _check_documentation(repo_contents)

                result = {
                    "has_comprehensive_tests": False,  # Can't determine without LLM
                    "shows_good_structure": has_structure,
                    "has_documentation": has_docs,
                    "notes": "Heuristic analysis (LLM unavailable)"
                }
                logging.info(f"[Code Quality] Heuristic analysis result: {result}")
                return result

        try:
            repo_contents = getattr(Data, "repo_contents", [])

            # If no repo contents (common for HF models without code repos),
            # return neutral score instead of 0.0
            if not isinstance(repo_contents, list) or len(repo_contents) == 0:
                logging.info("[Code Quality] No repository contents available, returning neutral score")
                return MetricResult(
                    metric_type=MetricType.CODE_QUALITY,
                    value=0.5,
                    details={
                        "mode": "no_repo",
                        "notes": "No repository contents available (neutral score)"
                    },
                    latency_ms=0,
                )

            has_tests = _check_test_files(repo_contents)
            has_dependency_mgmt = _check_dependency_management(repo_contents)

            llm_analysis = _analyze_code_with_llm(repo_contents)

            score = 0.0
            if has_tests:
                score += 0.4

            if llm_analysis["shows_good_structure"]:
                score += 0.3
            if has_dependency_mgmt:
                score += 0.3

            if score > 1.0:
                score = 1.0

            details = {
                "has_tests": has_tests,
                "has_dependency_management": has_dependency_mgmt,
                "lint_check_proxy": llm_analysis["shows_good_structure"],
                "llm_analysis": llm_analysis
            }

            return MetricResult(
                metric_type=MetricType.CODE_QUALITY,
                value=score,
                details=details,
                latency_ms=0,
            )

        except Exception as e:
            logging.error(f"Failed to evaluate code quality: {e}")
            raise RuntimeError("Code quality evaluation failed") from e

    def EvaluateDatasetsQuality(self, Data: Model) -> MetricResult:

        def _compose_dataset_text(data: Model) -> str:
            dataset_texts = []

            dataset_cards = getattr(data, "dataset_cards", {})
            dataset_infos = getattr(data, "dataset_infos", {})

            for dataset_id, card in dataset_cards.items():
                card_text = ""
                if card is not None:
                    card_text += f"Dataset: {dataset_id}\n"
                    card_text += f"Card Data: {str(card)}\n"

                if dataset_id in dataset_infos:
                    info = dataset_infos[dataset_id]
                    card_text += f"Dataset Info: {str(info)}\n"

                if card_text.strip():
                    dataset_texts.append(card_text)

            combined_text = "\n\n".join(dataset_texts)
            if len(combined_text) > 16000:
                combined_text = combined_text[:16000] + "\n\n...[truncated]..."

            return combined_text

        def _prepare_dataset_llm_prompt(data: Model) -> str:
            dataset_text = _compose_dataset_text(data)

            if not dataset_text.strip():
                return ""

            return (
                "CRITICAL: You MUST respond with ONLY valid JSON. "
                "No explanations, no markdown, no code blocks.\n\n"
                "Task: Evaluate these dataset cards for quality indicators. "
                "Return EXACTLY this JSON structure:\n\n"
                "{\n"
                '  "has_comprehensive_card": true|false,\n'
                '  "has_clear_data_source": true|false,\n'
                '  "has_preprocessing_info": true|false,\n'
                '  "has_large_size": false|true,\n'
                '  "notes": "analysis summary"\n'
                "}\n\n"
                "Rules:\n"
                "1. ONLY return JSON - nothing else\n"
                "2. Use true/false (lowercase) for booleans\n"
                "3. Keep notes under 30 characters\n\n"
                "Evaluation criteria:\n"
                "- has_comprehensive_card: Complete dataset cards with "
                "description, usage, citation?\n"
                "- has_clear_data_source: Specific data sources mentioned?\n"
                "- has_preprocessing_info: Evidence of data processing, "
                "filtering, quality control?\n"
                "- has_large_size: Dataset appears large (>10k samples)?\n\n"
                "Dataset information:\n"
                f"{dataset_text}\n\n"
                "Remember: ONLY return the JSON object."
            )

        def _parse_dataset_llm_response(response: str) -> Dict[str, Any]:
            try:
                obj = json.loads(response)
                return {
                    "has_comprehensive_card": bool(
                        obj.get("has_comprehensive_card", False)
                    ),
                    "has_clear_data_source": bool(
                        obj.get("has_clear_data_source", False)
                    ),
                    "has_preprocessing_info": bool(
                        obj.get("has_preprocessing_info", False)
                    ),
                    "has_large_size": bool(
                        obj.get("has_large_size", False)
                    ),
                    "notes": str(obj.get("notes", ""))[:400],
                }
            except Exception:
                return {
                    "has_comprehensive_card": False,
                    "has_clear_data_source": False,
                    "has_preprocessing_info": False,
                    "has_large_size": False,
                    "notes": "Failed to parse LLM response"
                }

        try:
            dataset_cards = getattr(Data, "dataset_cards", {})
            dataset_infos = getattr(Data, "dataset_infos", {})

            # If no dataset info, return neutral score (0.5) instead of 0.0
            # Many models don't have associated datasets in the system
            if not dataset_cards and not dataset_infos:
                logging.info("[Dataset Quality] No dataset info available, returning neutral score")
                return MetricResult(
                    metric_type=MetricType.DATASET_QUALITY,
                    value=0.5,
                    details={
                        "mode": "no_data",
                        "notes": "No dataset information available (neutral score)"
                    },
                    latency_ms=0,
                )

            prompt = _prepare_dataset_llm_prompt(Data)

            if not prompt:
                logging.info("[Dataset Quality] Empty dataset content, returning neutral score")
                return MetricResult(
                    metric_type=MetricType.DATASET_QUALITY,
                    value=0.5,
                    details={
                        "mode": "no_content",
                        "notes": "No dataset content to analyze (neutral score)"
                    },
                    latency_ms=0,
                )

            try:
                logging.info("[Dataset Quality] Calling LLM for dataset analysis...")
                response = self.llm_manager.call_genai_api(prompt)
                logging.info(f"[Dataset Quality] LLM response received")
                parsed = _parse_dataset_llm_response(response.content)

                score = 0.0
                if parsed["has_comprehensive_card"]:
                    score += 0.4
                if parsed["has_clear_data_source"]:
                    score += 0.2
                if parsed["has_preprocessing_info"]:
                    score += 0.2
                if parsed["has_large_size"]:
                    score += 0.2

                if score > 1.0:
                    score = 1.0

                details = {
                    "mode": "llm",
                    "dataset_count": len(dataset_cards),
                    **parsed
                }

                logging.info(f"[Dataset Quality] LLM analysis score: {score}")
                return MetricResult(
                    metric_type=MetricType.DATASET_QUALITY,
                    value=score,
                    details=details,
                    latency_ms=0,
                )

            except Exception as llm_error:
                # LLM failed - return neutral score
                logging.warning(f"[Dataset Quality] LLM analysis failed, returning neutral score: {llm_error}")
                return MetricResult(
                    metric_type=MetricType.DATASET_QUALITY,
                    value=0.5,
                    details={
                        "mode": "llm_failed",
                        "dataset_count": len(dataset_cards),
                        "notes": "LLM analysis failed (neutral score)"
                    },
                    latency_ms=0,
                )

        except Exception as e:
            logging.error(f"[Dataset Quality] Unexpected error: {e}")
            # Return neutral score instead of raising
            return MetricResult(
                metric_type=MetricType.DATASET_QUALITY,
                value=0.5,
                details={
                    "mode": "error",
                    "notes": f"Error: {str(e)[:100]}"
                },
                latency_ms=0,
            )

    def EvaluateRampUpTime(self, Data: Model) -> MetricResult:
        def _compose_source_text(data: Model) -> str:
            readme = ""
            path = getattr(data, "readme_path", None)
            if path:
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        readme = fh.read()
                except Exception:
                    readme = ""
            
            # IMPORTANT: Also include card content!
            card = ""
            card_obj = getattr(data, "card", None)
            if card_obj is not None:
                card = str(card_obj)
            
            text = (readme + "\n\n" + card).strip()
            if len(text) > 16000:
                text = text[:16000] + "\n\n...[truncated]..."
            return text

        def prepare_llm_prompt(data: Model) -> str:
            assert isinstance(data, Model)
            text = _compose_source_text(data)
            
            if not text.strip():
                # No documentation = return immediately with empty prompt
                return ""
            
            return (
                "You are evaluating documentation quality for ramp-up time. "
                "Be generous and recall-oriented.\n\n"
                "OUTPUT FORMAT: JSON ONLY\n\n"
                "Return this JSON format with scores from 0.0 to 1.0:\n\n"
                "{\n"
                '  "quality_of_example_code": 0.75,\n'
                '  "readme_coverage": 0.80,\n'
                '  "notes": "Brief rationale (max 100 chars)"\n'
                "}\n\n"
                "SCORING GUIDELINES (be generous!):\n\n"
                "quality_of_example_code (0.0 to 1.0):\n"
                "- 0.0-0.2: No code examples\n"
                "- 0.3-0.5: Minimal/incomplete examples\n"
                "- 0.6-0.8: Good working examples with imports\n"
                "- 0.9-1.0: Excellent, comprehensive, runnable examples\n\n"
                "readme_coverage (0.0 to 1.0):\n"
                "- 0.0-0.2: Minimal or no documentation\n"
                "- 0.3-0.5: Basic description, minimal structure\n"
                "- 0.6-0.8: Good coverage with installation, usage, examples\n"
                "- 0.9-1.0: Comprehensive docs with API reference, tutorials\n\n"
                "When uncertain, prefer higher scores. Good projects should score 0.7-0.9.\n\n"
                f"ANALYZE THIS DOCUMENTATION:\n{text[:6000]}\n\n"
                "RESPOND WITH JSON ONLY (no markdown, no commentary):"
            )

        def parse_llm_response(response: str) -> Dict[str, Any]:
            if not response or not response.strip():
                raise ValueError("Empty response from LLM")
            
            # Remove markdown code block markers if present
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            obj = json.loads(response)
            
            # Handle array values - take the first value if it's an array
            quality_val = obj.get("quality_of_example_code", 0.0)
            if isinstance(quality_val, list) and quality_val:
                quality_val = quality_val[0]
            
            readme_val = obj.get("readme_coverage", 0.0)
            if isinstance(readme_val, list) and readme_val:
                readme_val = readme_val[0]
            
            # Clamp values to [0.0, 1.0]
            quality_val = max(0.0, min(1.0, float(quality_val)))
            readme_val = max(0.0, min(1.0, float(readme_val)))
            
            return {
                "quality_of_example_code": quality_val,
                "readme_coverage": readme_val,
                "notes": str(obj.get("notes", ""))[:400],
            }

        try:
            logging.info("[Ramp-Up Time] Starting evaluation...")
            
            prompt = prepare_llm_prompt(Data)
            logging.info(f"[Ramp-Up Time] Prepared prompt (length: {len(prompt) if prompt else 0})")
            
            # Handle case with no documentation
            if not prompt:
                logging.warning("[Ramp-Up Time] No documentation found, returning 0.0")
                return MetricResult(
                    metric_type=MetricType.RAMP_UP_TIME,
                    value=0.0,
                    details={"mode": "no_docs", "reason": "No documentation found"},
                    latency_ms=0,
                )
            
            logging.info("[Ramp-Up Time] Calling LLM API...")
            response = self.llm_manager.call_genai_api(prompt)
            logging.info(f"[Ramp-Up Time] LLM response received")
            logging.info(f"[Ramp-Up Time] Response content: {repr(response.content[:500])}")
            
            logging.info("[Ramp-Up Time] Parsing LLM response...")
            parsed = parse_llm_response(response.content)
            logging.info(f"[Ramp-Up Time] Parsed result: {parsed}")

            # Calculate weighted average (50% each component)
            score = (parsed["quality_of_example_code"] * 0.5 + 
                    parsed["readme_coverage"] * 0.5)
            logging.debug(f"[Ramp-Up Time] Calculated score before clamping: {score}")
            
            # Ensure final score is in [0.0, 1.0]
            score = max(0.0, min(1.0, score))
            logging.info(f"[Ramp-Up Time] Final score: {score}")

            details = {"mode": "llm", **parsed}

            return MetricResult(
                metric_type=MetricType.RAMP_UP_TIME,
                value=score,
                details=details,
                latency_ms=0,
            )

        except Exception as exc:
            logging.error(f"[Ramp-Up Time] Evaluation failed with error: {exc}")
            logging.error(f"[Ramp-Up Time] Error type: {type(exc).__name__}")
            import traceback
            logging.error(f"[Ramp-Up Time] Traceback:\n{traceback.format_exc()}")
            raise RuntimeError("LLM evaluation failed") from exc

    def EvaluateLicense(self, Data: Model) -> MetricResult:
        def _get_license_info(data: Model) -> str:
            """Extract license information from all available sources"""
            license_info = []
            
            # Check model card for license information
            card_obj = getattr(data, "card", None)
            if card_obj and isinstance(card_obj, dict):
                # Common license fields in HuggingFace model cards
                license_fields = ["license", "license_name", "license_link",
                                  "license_url"]
                for field in license_fields:
                    if field in card_obj and card_obj[field]:
                        license_info.append(f"{field}: {card_obj[field]}")
                
                # Check description for license mentions
                description = card_obj.get("description", "")
                license_words = [
                    "license", "mit", "apache", "bsd", "gpl", "lgpl"
                ]
                if description and any(word in description.lower()
                                       for word in license_words):
                    license_info.append(f"description: {description}")
            
            # Check repository metadata for license
            repo_metadata = getattr(data, "repo_metadata", {})
            if isinstance(repo_metadata, dict):
                repo_license = repo_metadata.get("license")
                if repo_license:
                    if isinstance(repo_license, dict):
                        # GitHub API license object
                        license_name = repo_license.get("name", "")
                        license_key = repo_license.get("key", "")
                        if license_name or license_key:
                            license_info.append(
                                f"repo_license: {license_name} "
                                f"({license_key})")
                    else:
                        # Simple license string
                        license_info.append(f"repo_license: {repo_license}")
            
            return "\n".join(license_info) if license_info else ""

        def _classify_license(license_text: str) -> tuple:
            """Classify license and return (score, type, reason)"""
            if not license_text:
                return 0.0, "rule_based", "No license information found"
            
            license_lower = license_text.lower()
            
            # PERMISSIVE LICENSES -> 1.0 (EXACTLY 1.0!)
            permissive_licenses = {
                "mit": "MIT License",
                "bsd": "BSD License",
                "bsd-2-clause": "BSD 2-Clause License",
                "bsd-3-clause": "BSD 3-Clause License",
                "apache": "Apache License",
                "apache-2.0": "Apache License 2.0",
                "apache 2.0": "Apache License 2.0",
                "lgpl-2.1": "LGPL v2.1",
                "lgpl v2.1": "LGPL v2.1",
                "lgpl-3.0": "LGPL v3.0",
                "lgpl v3.0": "LGPL v3.0",
                "isc": "ISC License",
                "unlicense": "Unlicense"
            }
            
            for license_key, license_name in permissive_licenses.items():
                if license_key in license_lower:
                    return (1.0, "rule_based",
                            f"Permissive license: {license_name}")
            
            # RESTRICTIVE/INCOMPATIBLE LICENSES -> 0.0 (EXACTLY 0.0!)
            restrictive_licenses = {
                "gpl-2.0": "GPL v2.0",
                "gpl v2.0": "GPL v2.0",
                "gpl-3.0": "GPL v3.0",
                "gpl v3.0": "GPL v3.0",
                "cc by-nc": "Creative Commons Non-Commercial",
                "cc-by-nc": "Creative Commons Non-Commercial",
                "non-commercial": "Non-Commercial License",
                "proprietary": "Proprietary License",
                "all rights reserved": "All Rights Reserved"
            }
            
            for license_key, license_name in restrictive_licenses.items():
                if license_key in license_lower:
                    return (0.0, "rule_based",
                            f"Restrictive license: {license_name}")
            
            # If contains license keywords but unclassified -> use LLM
            license_keywords = ["license", "copyright", "terms", "conditions"]
            if any(keyword in license_lower for keyword in license_keywords):
                return (None, "llm_needed",
                        "Custom license requires LLM analysis")
            
            # No clear license information -> 0.0
            return 0.0, "rule_based", "Unclear or missing license information"

        def _prepare_llm_prompt(license_text: str) -> str:
            """Prepare LLM prompt for custom license analysis"""
            return (
                "OUTPUT FORMAT: JSON ONLY\n\n"
                "Analyze this license text for permissiveness. "
                "Return this JSON format:\n\n"
                "{\n"
                '  "permissiveness_score": 0.7,\n'
                '  "license_type": "Custom permissive",\n'
                '  "allows_commercial": true,\n'
                '  "allows_modification": true,\n'
                '  "notes": "Allows commercial use with attribution"\n'
                "}\n\n"
                "Scoring rules (STRICT):\n"
                "- 1.0: MIT/Apache/BSD-like (very permissive)\n"
                "- 0.8-0.9: Permissive with minor restrictions\n"
                "- 0.5-0.7: Some commercial/modification limits\n"
                "- 0.1-0.4: Significant restrictions\n"
                "- 0.0: GPL/Non-commercial/Highly restrictive\n\n"
                f"LICENSE TEXT:\n{license_text[:2000]}\n\n"
                "RESPOND WITH JSON ONLY:"
            )

        def _parse_llm_response(response: str) -> Dict[str, Any]:
            """Parse LLM response for license analysis"""
            try:
                obj = json.loads(response)
                return {
                    "permissiveness_score": float(
                        obj.get("permissiveness_score", 0.0)),
                    "license_type": str(obj.get("license_type", "Unknown")),
                    "allows_commercial": bool(
                        obj.get("allows_commercial", False)),
                    "allows_modification": bool(
                        obj.get("allows_modification", False)),
                    "notes": str(obj.get("notes", ""))[:200],
                }
            except Exception:
                return {
                    "permissiveness_score": 0.0,
                    "license_type": "Parse error",
                    "allows_commercial": False,
                    "allows_modification": False,
                    "notes": "Failed to parse LLM response"
                }

        try:
            # Extract license information from all sources
            license_text = _get_license_info(Data)
            
            # Attempt rule-based classification first
            score, classification_type, reason = _classify_license(
                license_text)
            
            if score is not None:
                # Successfully classified with rules
                details = {
                    "classification_method": classification_type,
                    "license_text": license_text[:500] if license_text else "",
                    "reason": reason,
                }
                
                return MetricResult(
                    metric_type=MetricType.LICENSE,
                    value=score,
                    details=details,
                    latency_ms=0,
                )
            
            else:
                # Need LLM analysis for custom license
                if not license_text:
                    return MetricResult(
                        metric_type=MetricType.LICENSE,
                        value=0.0,
                        details={"error": "No license information available"},
                        latency_ms=0,
                    )
                
                prompt = _prepare_llm_prompt(license_text)
                response = self.llm_manager.call_genai_api(prompt)
                logging.info(f"LLM license analysis: {response.content}")
                
                parsed = _parse_llm_response(response.content)
                
                # Ensure score is within valid range [0.0, 1.0]
                llm_score = max(0.0, min(1.0, parsed["permissiveness_score"]))
                
                details = {
                    "classification_method": "llm_analysis",
                    "license_text": license_text[:500],
                    "llm_analysis": parsed,
                }
                
                return MetricResult(
                    metric_type=MetricType.LICENSE,
                    value=llm_score,
                    details=details,
                    latency_ms=0,
                )

        except Exception as e:
            logging.error(f"Failed to evaluate license: {e}")
            raise RuntimeError("License evaluation failed") from e
        
    def EvaluateReproducibility(self, Data: Model) -> MetricResult:
        """
        Evaluate reproducibility based on demonstration code
        
        Per specification:
        "Whether the model can be run using only the demonstration code 
        included in the model card"
        
        Scoring:
        - 0.0: No demonstration code found OR code doesn't run
        - 0.5: Code runs with debugging/modifications
        - 1.0: Code runs with no changes needed
        
        Since we cannot actually execute the code, we assess based on:
        - Presence of runnable code examples
        - Completeness of the code (imports, setup, execution)
        - Documentation quality around the code
        """
        try:
            score = 0.0
            details = {}
            
            # Collect all text content
            combined_text = ""
            
            # Get README content
            if hasattr(Data, 'readme_path') and Data.readme_path:
                try:
                    with open(Data.readme_path, 'r', encoding='utf-8') as f:
                        combined_text += f.read() + "\n"
                except Exception as e:
                    logging.debug(f"Could not read README: {e}")
            
            # Get card content
            if hasattr(Data, 'card') and Data.card:
                combined_text += str(Data.card) + "\n"
            
            # Convert to lowercase for checking
            text_lower = combined_text.lower()
            
            # If no content, return 0
            if not combined_text.strip():
                return MetricResult(
                    metric_type=MetricType.PERFORMANCE_CLAIMS,  # TODO: Add REPRODUCIBILITY
                    value=0.0,
                    details={
                        "reason": "No documentation found",
                        "has_code": False
                    },
                    latency_ms=0
                )
            
            # Check for demonstration code
            has_code_block = False
            has_complete_example = False
            
            # Look for code blocks (markdown format)
            import re
            code_blocks = re.findall(r'```[\s\S]*?```', combined_text)
            
            if code_blocks:
                has_code_block = True
                details['code_blocks_found'] = len(code_blocks)
                
                # Check if code blocks contain actual Python/model code
                for block in code_blocks:
                    block_lower = block.lower()
                    
                    # Check for model execution patterns
                    execution_indicators = [
                        'import',           # Has imports
                        'from',             # Has imports
                        'model',            # References model
                        'predict',          # Shows prediction
                        'inference',        # Shows inference
                        'generate',         # Generation
                        '.forward(',        # Forward pass
                        'tokenizer',        # Tokenization
                        'pipeline(',        # Pipeline usage
                    ]
                    
                    indicators_found = sum(1 for ind in execution_indicators 
                                        if ind in block_lower)
                    
                    # If code block has multiple execution indicators, it's complete
                    if indicators_found >= 3:
                        has_complete_example = True
                        details['execution_indicators_found'] = indicators_found
                        break
            
            # Also check for inline code examples
            if not has_code_block:
                inline_code = re.findall(r'`[^`]+`', combined_text)
                if inline_code:
                    has_code_block = True
                    details['inline_code_found'] = len(inline_code)
            
            # Determine score based on code quality
            if not has_code_block:
                # No demonstration code found
                score = 0.0
                details['reason'] = "No demonstration code found"
                details['has_code'] = False
                
            elif has_complete_example:
                # Complete example with imports and execution
                score = 1.0
                details['reason'] = "Complete demonstration code with imports and execution"
                details['has_code'] = True
                details['code_completeness'] = "complete"
                
            else:
                # Has code but incomplete or would need debugging
                score = 0.5
                details['reason'] = "Demonstration code present but may need debugging"
                details['has_code'] = True
                details['code_completeness'] = "partial"
            
            # Additional checks to validate the score
            if score > 0:
                # Check for common issues that would require debugging
                issues = []
                
                # Missing dependencies/imports section
                if 'install' not in text_lower and 'requirements' not in text_lower:
                    if 'pip' not in text_lower and 'conda' not in text_lower:
                        issues.append("No installation instructions")
                
                # Missing model loading instructions
                if score == 1.0:
                    if 'load' not in text_lower and 'from_pretrained' not in text_lower:
                        issues.append("Unclear model loading")
                
                # If there are issues, downgrade from 1.0 to 0.5
                if issues and score == 1.0:
                    score = 0.5
                    details['issues_found'] = issues
                    details['reason'] = "Code present but has issues: " + ", ".join(issues)
            
            return MetricResult(
                metric_type=MetricType.PERFORMANCE_CLAIMS,  # TODO: Add REPRODUCIBILITY
                value=score,
                details=details,
                latency_ms=0,
                error=None
            )
            
        except Exception as e:
            logging.error(f"Failed to evaluate reproducibility: {e}")
            return MetricResult(
                metric_type=MetricType.PERFORMANCE_CLAIMS,
                value=0.0,
                details={
                    "error": str(e),
                    "reason": "Evaluation failed",
                    "has_code": False
                },
                latency_ms=0,
                error=str(e)
            )