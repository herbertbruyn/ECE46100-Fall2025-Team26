from dotenv import load_dotenv
import logging
import time
import os
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Tuple, Dict
from Controllers.Controller import Controller
from Services.Metric_Model_Service import ModelMetricService
from lib.Metric_Result import MetricResult

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Configure logging to hide all debug info
logging.basicConfig(level=logging.CRITICAL)


def time_evaluation(eval_func: Callable, *args, **kwargs) -> \
        Tuple[MetricResult, float]:
    """
    Times a single evaluation function and returns the result and execution
    time.
    
    Args:
        eval_func: The evaluation function to time
        *args: Arguments to pass to the evaluation function
        **kwargs: Keyword arguments to pass to the evaluation function
    
    Returns:
        Tuple containing (MetricResult, execution_time_in_seconds)
    """
    start_time = time.perf_counter()
    try:
        result = eval_func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        return result, execution_time
    except Exception as e:
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        logging.error(f"Error in evaluation {eval_func.__name__}: {e}")
        raise


def run_evaluations_sequential(model_data) -> \
        Dict[str, Tuple[MetricResult, float]]:
    """
    Run all evaluations sequentially and time each one.
    
    Args:
        model_data: The model data to evaluate
        
    Returns:
        Dictionary mapping evaluation names to (result, time) tuples
    """
    service = ModelMetricService()
    results = {}
    
    # Define all evaluations
    evaluations = [
        ("Performance Claims", service.EvaluatePerformanceClaims),
        ("Bus Factor", service.EvaluateBusFactor),
        ("Size", service.EvaluateSize),
        ("Ramp-Up Time", service.EvaluateRampUpTime),
        ("Availability", service.EvaluateDatasetAndCodeAvailabilityScore),
        ("Code Quality", service.EvaluateCodeQuality),
        ("Dataset Quality", service.EvaluateDatasetsQuality),
        ("License", service.EvaluateLicense),
        ("Reproducibility", service.EvaluateReproducibility)
    ]
    
    logging.info("Running evaluations sequentially...")
    logging.info("-" * 50)
    
    for name, eval_func in evaluations:
        logging.info(f"Starting: {name}")
        result, exec_time = time_evaluation(eval_func, model_data)
        results[name] = (result, exec_time)
        logging.info(f"Completed: {name} - Score: {result.value:.3f} - "
                     f"Time: {exec_time:.3f}s")
    
    return results


def run_evaluations_parallel(model_data, max_workers: int = 2) -> \
        Dict[str, Tuple[MetricResult, float]]:
    """
    Run all evaluations in parallel using ThreadPoolExecutor and time each one.

    Args:
        model_data: The model data to evaluate
        max_workers: Maximum number of worker threads (default: 2)

    Returns:
        Dictionary mapping evaluation names to (result, time) tuples
    """
    service = ModelMetricService()
    results = {}

    # Define all evaluations
    evaluations = [
        ("Performance Claims", service.EvaluatePerformanceClaims),
        ("Bus Factor", service.EvaluateBusFactor),
        ("Size", service.EvaluateSize),
        ("Ramp-Up Time", service.EvaluateRampUpTime),
        ("Availability", service.EvaluateDatasetAndCodeAvailabilityScore),
        ("Code Quality", service.EvaluateCodeQuality),
        ("Dataset Quality", service.EvaluateDatasetsQuality),
        ("License", service.EvaluateLicense),
        ("Reproducibility", service.EvaluateReproducibility)
    ]
    
    logging.info(f"Running evaluations in parallel "
                 f"(max_workers={max_workers})...")
    logging.info("-" * 50)
    
    # Submit all tasks to the thread pool
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all evaluations
        future_to_name = {}
        for name, eval_func in evaluations:
            future = executor.submit(time_evaluation, eval_func, model_data)
            future_to_name[future] = name
            logging.info(f"Submitted: {name}")
        
        # Collect results as they complete
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                result, exec_time = future.result()
                results[name] = (result, exec_time)
                logging.info(f"Completed: {name} - "
                             f"Score: {result.value:.3f} - "
                             f"Time: {exec_time:.3f}s")
            except Exception as e:
                logging.error(f"Failed: {name} - Error: {e}")
                # You might want to store the error in results or handle
                # it differently
                
    return results


def print_timing_summary(results: Dict[str, Tuple[MetricResult, float]],
                         total_time: float):
    """
    Print a summary of all evaluation results and timing information.
    
    Args:
        results: Dictionary mapping evaluation names to (result, time) tuples
        total_time: Total execution time for all evaluations
    """
    logging.info("\n" + "=" * 60)
    logging.info("EVALUATION SUMMARY")
    logging.info("=" * 60)
    
    total_eval_time = 0.0
    for name, (result, exec_time) in results.items():
        logging.info(f"{name:<20}: Score = {result.value:.3f}, "
                     f"Time = {exec_time:.3f}s")
        total_eval_time += exec_time
    
    logging.info("-" * 60)
    logging.info(f"{'Total Eval Time':<20}: {total_eval_time:.3f}s")
    logging.info(f"{'Wall Clock Time':<20}: {total_time:.3f}s")
    
    if total_time > 0:
        efficiency = (total_eval_time / total_time) * 100
        logging.info(f"{'Parallelism Efficiency':<20}: {efficiency:.1f}%")
    
    logging.info("=" * 60)


def parse_input(file_path):
    """
    Parse input file with lines like:
    [code_link], [dataset_link], model_link
    Returns a list of dicts with keys: dataset_link, code_link, model_link
    """
    jobs = []
    # If the file path is relative, resolve it relative to the project root
    if not os.path.isabs(file_path):
        # Get the project root directory (two levels up from this file)
        project_root = os.path.join(os.path.dirname(__file__), '..', '..')
        file_path = os.path.join(project_root, file_path)
        file_path = os.path.normpath(file_path)
    
    with open(file_path, encoding='utf-8') as f:
        for row in csv.reader(f):
            # Remove whitespace and ignore empty fields
            row = [x.strip() for x in row if x.strip()]
            if not row:
                continue
            # Always take the last field as model_link
            model_link = row[-1]
            code_link = row[0] if len(row) > 1 else None
            dataset_link = row[1] if len(row) > 2 else None
            jobs.append({
                'model_link': model_link,
                'dataset_link': dataset_link,
                'code_link': code_link
            })
    return jobs


def find_missing_links(model_link, dataset_link, code_link):
    """
    If dataset_link or code_link is missing, try to find them from the
    model card. Uses HuggingFace API to get model info and parse for links.
    """
    from lib.HuggingFace_API_Manager import HuggingFaceAPIManager
    import re
    
    discovered_datasets = []
    discovered_code = None
    
    try:
        # Initialize HuggingFace API manager
        hf_manager = HuggingFaceAPIManager()
        
        # Extract model ID from the link
        model_id = hf_manager.model_link_to_id(model_link)
        logging.info(f"  Searching for links in model: {model_id}")
        
        # Get model information
        model_info = hf_manager.get_model_info(model_id)
        
        # Check model card text for links
        if hasattr(model_info, 'cardData') and model_info.cardData:
            card_text = str(model_info.cardData)
            
            # Look for dataset links in model card
            dataset_patterns = [
                r'https://huggingface\.co/datasets/([^/\s]+/[^/\s]+)',
                r'huggingface\.co/datasets/([^/\s]+/[^/\s]+)',
                r'datasets/([^/\s\)]+/[^/\s\)]+)',
            ]
            
            for pattern in dataset_patterns:
                matches = re.findall(pattern, card_text, re.IGNORECASE)
                for match in matches:
                    if not match.startswith('http'):
                        dataset_url = (f"https://huggingface.co/datasets/"
                                       f"{match}")
                    else:
                        dataset_url = match
                    if dataset_url not in discovered_datasets:
                        discovered_datasets.append(dataset_url)
            
            # Look for GitHub/code repository links
            code_patterns = [
                r'https://github\.com/([^/\s\)]+/[^/\s\)]+)',
                r'github\.com/([^/\s\)]+/[^/\s\)]+)',
                r'\[.*?\]\(https://github\.com/([^/\s\)]+/[^/\s\)]+)\)',
                r'repo:\s*([^/\s]+/[^/\s]+)',
                r'code:\s*https://github\.com/([^/\s\)]+/[^/\s\)]+)',
            ]
            
            for pattern in code_patterns:
                matches = re.findall(pattern, card_text, re.IGNORECASE)
                if matches and not discovered_code:
                    match = matches[0]  # Take the first one
                    # Clean up the match (remove trailing punctuation)
                    match = match.rstrip('.,;)')
                    if not match.startswith('http'):
                        discovered_code = f"https://github.com/{match}"
                    else:
                        discovered_code = match
                    break
        
        # Also check model tags and metadata
        if hasattr(model_info, 'tags') and model_info.tags:
            for tag in model_info.tags:
                if 'dataset:' in tag:
                    dataset_name = tag.replace('dataset:', '').strip()
                    if '/' in dataset_name:
                        dataset_url = (f"https://huggingface.co/datasets/"
                                       f"{dataset_name}")
                        if dataset_url not in discovered_datasets:
                            discovered_datasets.append(dataset_url)
        
        # Check model info for repository URL
        if hasattr(model_info, 'modelId') and not discovered_code:
            # Try to find associated GitHub repo through common naming
            model_id_parts = model_info.modelId.split('/')
            if len(model_id_parts) == 2:
                org, model_name = model_id_parts
                # Try common GitHub URL patterns
                # Remove size/version suffixes (e.g., -medium, -large, -32B)
                pattern = r'-(?:small|medium|large|xl|xxl|\d+[BMG]?)$'
                base_name = re.sub(pattern, '', model_name,
                                   flags=re.IGNORECASE)
                
                potential_repos = [
                    f"https://github.com/{org}/{base_name}",
                    f"https://github.com/{org}/{model_name}",
                    f"https://github.com/{org}/{model_name.lower()}",
                    f"https://github.com/{org.lower()}/{base_name}",
                ]
                # We'll check if these exist later, for now just take first
                discovered_code = potential_repos[0]
        
    except Exception as e:
        logging.warning(f"Could not fetch model info for {model_link}: {e}")
    
    # Use provided links first, fall back to discovered links
    final_dataset_links = []
    if dataset_link and dataset_link.strip():
        final_dataset_links.append(dataset_link.strip())
    final_dataset_links.extend(discovered_datasets)
    
    final_code_link = code_link
    if not final_code_link or not final_code_link.strip():
        final_code_link = discovered_code
    
    # Report what we found
    if discovered_datasets:
        dataset_preview = ', '.join(discovered_datasets[:3])
        more_text = '...' if len(discovered_datasets) > 3 else ''
        logging.info(f"  Found {len(discovered_datasets)} dataset link(s): "
                     f"{dataset_preview}{more_text}")
    if discovered_code:
        logging.info(f"  Found code repository: {discovered_code}")
    
    return final_dataset_links, final_code_link


def extract_model_name(model_link):
    """Extract model name from HuggingFace model link."""
    import re
    match = re.search(r'huggingface\.co/([^/]+/[^/?]+)', model_link)
    if match:
        return match.group(1).split('/')[-1]
    return "unknown_model"


def format_size_score(size_result):
    """Convert size score to platform-specific format."""
    # For now, create a simple mapping based on the size score
    # This might need adjustment based on actual size evaluation logic
    base_score = size_result.value
    return {
        "raspberry_pi": round(min(base_score * 0.2, 1.0), 2),
        "jetson_nano": round(min(base_score * 0.4, 1.0), 2),
        "desktop_pc": round(min(base_score * 0.8, 1.0), 2),
        "aws_server": round(base_score, 2)
    }


def run_batch_evaluation(input_file):
    jobs = parse_input(input_file)
    for i, job in enumerate(jobs, 1):
        model_link = job['model_link']
        
        dataset_links, code_link = find_missing_links(
            model_link, job.get('dataset_link'), job.get('code_link'))
        
        fetcher = Controller()
        model_data = fetcher.fetch(
            model_link,
            dataset_links=dataset_links if dataset_links else [],
            code_link=code_link
        )
        
        start_time = time.perf_counter()
        # Use max_workers=2 for free-tier EC2 to balance speed and stability
        results = run_evaluations_parallel(model_data, max_workers=2)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        
        # Extract model name
        model_name = extract_model_name(model_link)
        
        # Store metric scores for net score calculation
        metric_scores = {}
        
        # Add each metric with proper naming and latency
        metric_mapping = {
            "Ramp-Up Time": ("ramp_up_time", "ramp_up_time_latency"),
            "Bus Factor": ("bus_factor", "bus_factor_latency"),
            "Performance Claims": ("performance_claims",
                                   "performance_claims_latency"),
            "License": ("license", "license_latency"),
            "Size": ("size_score", "size_score_latency"),
            "Availability": ("dataset_and_code_score",
                             "dataset_and_code_score_latency"),
            "Dataset Quality": ("dataset_quality", "dataset_quality_latency"),
            "Code Quality": ("code_quality", "code_quality_latency")
        }
        
        # Collect all metric data first
        metric_data = {}
        for metric_name, (result, exec_time) in results.items():
            if metric_name in metric_mapping:
                if metric_name == "Size":
                    # Special handling for size score
                    size_scores = format_size_score(result)
                    metric_data[metric_name] = (size_scores, exec_time)
                    # Calculate mean of all platform scores for net score
                    size_mean = sum(size_scores.values()) / len(size_scores)
                    metric_scores["Size"] = size_mean
                else:
                    score_value = round(result.value, 2)
                    metric_data[metric_name] = (score_value, exec_time)
                    metric_scores[metric_name] = score_value
        
        # Calculate net score using the specified weights
        # NetScore = 0.20RampUp + 0.15BusFactor + 0.15PerfClaim + 0.15License +
        #           0.10Size + 0.10CodeDatasetAvailability + 0.10DatasetQual +
        #           0.05CodeQual
        weights = {
            "Ramp-Up Time": 0.20,
            "Bus Factor": 0.15,
            "Performance Claims": 0.15,
            "License": 0.15,
            "Size": 0.10,
            "Availability": 0.10,
            "Dataset Quality": 0.10,
            "Code Quality": 0.05
        }
        
        net_score = 0.0
        for metric_name, weight in weights.items():
            if metric_name in metric_scores:
                net_score += weights[metric_name] * metric_scores[metric_name]
        
        # Build output JSON in the exact order as sample_output.txt
        from collections import OrderedDict
        output = OrderedDict([
            ("name", model_name),
            ("category", "MODEL"),
            ("net_score", round(net_score, 2)),
            ("net_score_latency", int(total_time * 1000)),
        ])
        
        # Add metrics in the exact order from sample output
        ordered_metrics = [
            "Ramp-Up Time", "Bus Factor", "Performance Claims", "License",
            "Size", "Availability", "Dataset Quality", "Code Quality"
        ]
        
        for metric_name in ordered_metrics:
            if metric_name in metric_data:
                score_key, latency_key = metric_mapping[metric_name]
                score_value, exec_time = metric_data[metric_name]
                
                output[score_key] = score_value
                output[latency_key] = int(exec_time * 1000)
        
        # Output JSON to stdout
        import json
        json_output = json.dumps(output, separators=(',', ':'),
                                 ensure_ascii=False)
        print(json_output.strip())


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1].endswith('.txt'):
        run_batch_evaluation(sys.argv[1])
    else:
        # error: please provide a .txt file with model links
        logging.error("Usage: python main.py sample_input.txt")
