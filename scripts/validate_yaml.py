import os
import sys
import yaml
import re
from pathlib import Path
import subprocess
import json

def comment_on_pr(message):
    comment = {
        "body": message
    }
    pr_number = os.getenv('PR_NUMBER')
    subprocess.run(['gh', 'pr', 'comment', pr_number, '--body', message])

def validate_yaml(file_path):
    with open(file_path) as f:
        config = yaml.safe_load(f)

    errors = []
    
    # 1. Validate author
    pr_author = os.getenv('PR_AUTHOR')
    if config.get('author') != pr_author:
        errors.append(f"Author should be '{pr_author}', found '{config.get('author')}'")

    # 2. Validate task
    folder_name = Path(file_path).parent.name
    if config.get('task') != folder_name:
        errors.append(f"Task should be '{folder_name}', found '{config.get('task')}'")

    # 3. Validate keywords
    keywords = config.get('keywords', [])
    if not keywords or not isinstance(keywords, list) or not all(isinstance(k, str) and k.islower() for k in keywords):
        errors.append("Keywords should be a non-empty list of lowercase strings")

    # 4. Validate description
    desc = config.get('description', '')
    if not desc or not isinstance(desc, str) or len(desc.split()) > 1000:
        errors.append("Description should be a non-empty string with maximum 1000 words")

    # 5. Validate min_version
    min_version = config.get('min_version')
    if not min_version:
        errors.append("min_version is required")
    else:
        try:
            subprocess.run(['git', 'clone', 'https://github.com/ultralytics/ultralytics'], check=True)
            os.chdir('ultralytics')
            subprocess.run(['git', 'checkout', f'tags/v{min_version}'], check=True)
            subprocess.run(['pip', 'install', '-e', '.'], check=True)
        except subprocess.CalledProcessError:
            errors.append(f"Invalid min_version: {min_version}")

    # 6-7. Validate model, FLOPs, parameters, and strides
    try:
        from ultralytics import YOLO
        model = YOLO(file_path)
        _, params, _, flops = model.info()
        
        if abs(flops - config.get('flops', 0)) > 0.1:
            errors.append(f"FLOPs mismatch: expected {config.get('flops')}, got {flops:.1f}")
        
        if params != config.get('parameters', 0):
            errors.append(f"Parameters mismatch: expected {config.get('parameters')}, got {params}")
        
        # Validate strides
        import torch
        model.model.model[-1] = torch.nn.Identity()
        imgsz = 640
        out = model.model(torch.randn(1, 3, imgsz, imgsz))
        computed_strides = [imgsz // o.shape[-1] for o in out]
        
        if computed_strides != config.get('strides', []):
            errors.append(f"Strides mismatch: expected {config.get('strides')}, got {computed_strides}")
    except Exception as e:
        errors.append(f"Failed to load model with min_version {min_version}: {str(e)}")

    # 8. Validate nc
    nc = config.get('nc', 0)
    if not isinstance(nc, int) or nc <= 0:
        errors.append("nc must be an integer greater than 0")

    if errors:
        comment_on_pr("\n".join(["YAML validation failed:"] + errors))
        sys.exit(1)

def main():
    for file in os.getenv('CFG_ALL_CHANGED_FILES').split():
        if file.endswith(('.yaml', '.yml')):
            validate_yaml(file)