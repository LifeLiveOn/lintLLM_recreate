"""
Utility functions for the Verilog analysis project
"""
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
import os
import csv
import re


class Timer:
    """Helper class for timing operations"""

    def __init__(self, name: str = "Operation"):
        self.name = name
        self.start_time = None
        self.end_time = None

    def start(self) -> str:
        """Start the timer and return formatted start time"""
        self.start_time = datetime.now()
        formatted_time = self.start_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        return formatted_time

    def end(self) -> tuple[str, float]:
        """End the timer and return formatted end time and duration in seconds"""
        self.end_time = datetime.now()
        formatted_time = self.end_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        duration = (self.end_time - self.start_time).total_seconds()
        return formatted_time, duration

    def get_duration(self) -> float:
        """Get duration without ending the timer"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


def validate_file_path(file_path: str) -> bool:
    """Check if a file exists"""
    return os.path.exists(file_path)


def format_result_message(module_name: str, result: Dict[Any, Any]) -> str:
    """Format LLM analysis result for display"""
    if result and 'message' in result and 'content' in result['message']:
        return f"Analysis result for {module_name}: {result['message']['content']}"
    elif 'error' in result:
        return f"Error analyzing {module_name}: {result['error']}"
    else:
        return f"Unknown result format for {module_name}: {result}"


def parse_llm_result(result: Dict[Any, Any]) -> Tuple[Optional[str], Optional[str], str]:
    """
    Parse LLM result to extract defect information

    Returns:
        Tuple of (defect_line, defect_category, defect_description)
        defect_line can be single line number or multiple lines separated by '-'
    """
    if 'error' in result:
        return None, "ERROR", result['error']

    if not (result and 'message' in result and 'content' in result['message']):
        return None, "UNKNOWN", "Unknown result format"

    content = result['message']['content']

    # Check if there are defects
    if "RESULT: [NO]" in content:
        return None, "NONE", "No defects found"

    # Check for multiple defects first
    is_multiple = "MULTIPLE DEFECTS: [YES]" in content

    defect_line = None
    if is_multiple:
        # Extract all defect lines (format: line1-line2-line3)
        all_lines_match = re.search(
            r'ALL DEFECT LINES:\s*\[([0-9\-]+)\]', content)
        if all_lines_match:
            defect_line = all_lines_match.group(1)

        # Also try to extract main defect line for category determination
        main_line_match = re.search(r'MAIN DEFECT LINE:\s*\[(\d+)\]', content)
        main_line = main_line_match.group(1) if main_line_match else None
    else:
        # Single defect - extract defect line
        defect_line_match = re.search(r'DEFECT LINE:\s*\[(\d+)\]', content)
        if defect_line_match:
            defect_line = defect_line_match.group(1)
            main_line = defect_line
        else:
            main_line = None

    # Extract defect category if present (new format)
    defect_category = None
    defect_category_match = re.search(
        r'DEFECT CATEGORY:\s*\[?([A-Z_]+)\]?', content)
    if defect_category_match:
        defect_category = defect_category_match.group(1)

    # Extract description if present (new format)
    description = ""
    description_match = re.search(
        r'DESCRIPTION:\s*(.+?)(?:\n|$)', content, re.DOTALL)
    if description_match:
        description = description_match.group(1).strip()
        # Keep description concise - limit to first sentence or 100 characters
        if '.' in description:
            description = description.split('.')[0] + '.'
        elif len(description) > 100:
            description = description[:97] + '...'

    # If no structured category found, fall back to content-based detection
    if not defect_category:
        defect_category = "UNKNOWN"

    # If no structured description found, use cleaned content
    if not description:
        description = content.replace(
            "RESULT: [YES]", "").replace("RESULT: [NO]", "")
        if "MULTIPLE DEFECTS:" in content:
            description = re.sub(
                r'MULTIPLE DEFECTS:.*?(?=\n|$)', '', description)
        if "ALL DEFECT LINES:" in content:
            description = re.sub(
                r'ALL DEFECT LINES:.*?(?=\n|$)', '', description)
        if "MAIN DEFECT LINE:" in content:
            description = re.sub(
                r'MAIN DEFECT LINE:.*?(?=\n|$)', '', description)
        if "DEFECT LINE:" in content:
            description = re.sub(r'DEFECT LINE:.*?(?=\n|$)', '', description)
        if "DEFECT CATEGORY:" in content:
            description = re.sub(
                r'DEFECT CATEGORY:.*?(?=\n|$)', '', description)

        description = re.sub(r'\s+', ' ', description).strip()

        # Keep description concise
        if len(description) > 100:
            description = description[:97] + '...'

    return defect_line, defect_category, description


def write_to_csv(csv_filename: str, level: str, file_name: str, defect_line: Optional[str],
                 defect_type: str, defect_description: str) -> None:
    """
    Write analysis result to CSV file

    Args:
        csv_filename: Name of the CSV file
        level: Level of complexity (simple, medium, complex)
        file_name: Verilog file name
        defect_line: Line number where defect was found (None if no defect)
        defect_type: Type of defect found
        defect_description: Description of the defect
    """
    file_exists = os.path.exists(csv_filename)

    with open(csv_filename, 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Level', 'File_Name', 'Defect_Line',
                      'Defect_Type', 'Defect_Description']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Write header if file is new
        if not file_exists:
            writer.writeheader()

        writer.writerow({
            'Level': level,
            'File_Name': file_name,
            'Defect_Line': defect_line if defect_line else 'N/A',
            'Defect_Type': defect_type,
            'Defect_Description': defect_description
        })


def build_verilog_path(base_path: str, module_name: str) -> str:
    """Build the full path to a Verilog file"""
    return os.path.join(base_path, f"{module_name}.v")


class Config:
    """Configuration constants"""
    OLLAMA_API = "http://localhost:11434/api/chat"
    HEADERS = {"Content-Type": "application/json"}
    MODEL_NAME = "qwen3:14b"
    MAX_TOKENS = 2048

    TEMPERATURE = 0
    TIMEOUT = 30

    # Dataset configuration
    MODULE_START_INDEX = 1
    MODULE_END_INDEX = 31  # exclusive
    PROJECT_PREFIXES = ['simple_', 'medium_', 'complex_']
    FOLDER_NAMES = ['simple', 'medium', 'complex']
    BASE_BENCHMARK_PATH = 'Static-Verilog-Analysis/Benchmark'
