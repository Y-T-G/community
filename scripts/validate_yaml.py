import os
import sys
import yaml
import requests
from pathlib import Path
import subprocess

def comment_on_pr(message):
    pr_number = os.getenv('PR_NUMBER')
    repo = os.getenv('GITHUB_REPOSITORY')
    token = os.getenv('GITHUB_TOKEN')

    if not all([pr_number, repo, token]):
        print("Missing environment variables for commenting on PR.")
        return

    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }
    payload = {
        "body": message
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 201:
        print("Comment posted successfully.")
    else:
        print(f"Failed to post comment: {response.status_code} - {response.text}")

def validate_yaml(file_path):
    with open(file_path) as f:
        config = yaml.safe_load(f)

    errors = []
    
    # Validate author
    pr_author = os.getenv('PR_AUTHOR')
    if config.get('author') != pr_author:
        errors.append(f"Author should be '{pr_author}', found '{config.get('author')}'")

    # Validate task
    folder_name = Path(file_path).parent.name
    if config.get('task') != folder_name:
        errors.append(f"Task should be '{folder_name}', found '{config.get('task')}'")

    # Validate keywords
    keywords = config.get('keywords', [])
    if not keywords or not isinstance(keywords, list) or not all(isinstance(k, str) and k.islower() for k in keywords):
        errors.append("Keywords should be a non-empty list of lowercase strings")

    # Validate description
    desc = config.get('description', '')
    if not desc or not isinstance(desc, str) or len(desc.split()) > 1000:
        errors.append("Description should be a non-empty string with maximum 1000 words")

    # Validate min_version
    min_version = config.get('min_version')
    if not min_version:
        errors.append("min_version is required")
    else:
        try:
            if not os.path.isdir('ultralytics'):
                subprocess.run(['git', 'clone', 'https://github.com/ultralytics/ultralytics'], check=True)
            else:
                print("ultralytics directory already exists. Skipping clone.")
            os.chdir('ultralytics')
            subprocess.run(['git', 'checkout', f'tags/v{min_version}'], check=True)
            subprocess.run(['pip', 'install', '-e', '.'], check=True)
        except subprocess.CalledProcessError:
            errors.append(f"Invalid min_version: {min_version}")

    # Validate model, FLOPs, parameters, and strides
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
        head = model.model.model[-1]
        f, i = head.f, head.i
        head = torch.nn.Identity()
        head.f, head.i = f, i
        model.model.model[-1] = head
        imgsz = 640
        out = model.model(torch.randn(1, 3, imgsz, imgsz))
        computed_strides = [imgsz // o.shape[-1] for o in out]
        
        if computed_strides != config.get('strides', []):
            errors.append(f"Strides mismatch: expected {config.get('strides')}, got {computed_strides}")
    except Exception as e:
        errors.append(f"Failed to load model with min_version {min_version}: {str(e)}")

    # Validate nc
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

if __name__ == "__main__":
    main()