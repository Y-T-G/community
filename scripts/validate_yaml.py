import os
import sys
import yaml
import requests
from pathlib import Path
import subprocess
import traceback


def comment_on_pr(message):
    pr_number = os.getenv("PR_NUMBER")
    repo = os.getenv("GITHUB_REPOSITORY")
    token = os.getenv("GITHUB_TOKEN")

    if not all([pr_number, repo, token]):
        print("Missing environment variables for commenting on PR.")
        return

    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    payload = {"body": message}

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 201:
        print("Comment posted successfully.")
    else:
        print(f"Failed to post comment: {response.status_code} - {response.text}")


def get_output_shapes(model):
    import torch

    ori_len = len(model.model.model)
    shape_list = []
    layers = [
        str(layer).replace("'", "")
        for layer in model.yaml["backbone"] + model.yaml["head"]
    ]

    for i in range(ori_len):
        model.model.model = model.model.model[:-1] if i > 0 else model.model.model
        out = model.model(torch.randn(1, 3, 640, 640))
        if isinstance(out, torch.Tensor):
            shape_list.append(
                f"  - {layers[-1 - i]}  # {tuple(out.shape)} - {ori_len - i - 1}"
            )
        else:
            shape_list.append(f"  - {layers[-1 - i]}  # {ori_len - i - 1}")

    max_len = max(len(s.split("  #")[0]) for s in shape_list)
    formatted = [
        s.split("  #")[0].ljust(max_len + 4) + "# " + s.split("  #")[1]
        for s in shape_list
    ]
    formatted = list(reversed(formatted))
    formatted.insert(0, "backbone:")
    formatted.insert(1, "  # [from, repeats, module, args]")
    formatted.insert(len(model.yaml["backbone"]) + 2, "head:")
    return formatted


def insert_scale_letter(file_path: str, scale: str) -> str:
    """
    "yolo11-p2.yaml" + "n" → "/…/yolo11n-p2.yaml"
    Ultralytics reads this scale from filename.
    """
    p = Path(file_path)
    stem, suffix = p.stem, p.suffix  # e.g. "yolo11-p2", ".yaml"
    base, rest = stem.split("-" if "-" in stem else ".", 1)  # "yolo11", "p2"
    return str(p.with_name(f"{base}{scale}-{rest}{suffix}"))


def validate_yaml(file_path):
    with open(file_path) as f:
        config = yaml.safe_load(f)

    errors = []

    # Validate author
    pr_author = os.getenv("PR_AUTHOR")
    if config.get("author") != pr_author:
        errors.append(
            f"👤 **Author**: Expected `{pr_author}`, got `{config.get('author')}`"
        )

    # Validate task
    folder_name = Path(file_path).parent.name
    filename = Path(file_path).name
    if config.get("task") != folder_name:
        errors.append(
            f"📋 **Task**: Expected `{folder_name}`, got `{config.get('task')}`"
        )

    # Validate keywords
    keywords = config.get("keywords", [])
    if (
        not keywords
        or not isinstance(keywords, list)
        or not all(isinstance(k, str) and k.islower() for k in keywords)
    ):
        errors.append("🏷️ **Keywords**: Must be a non-empty list of lowercase strings")

    # Validate description
    desc = config.get("description", "")
    if not desc or not isinstance(desc, str) or len(desc.split()) > 1000:
        errors.append(
            "📝 **Description**: Must be a non-empty string with maximum 1000 words"
        )

    # Validate min_version
    min_version = config.get("min_version")
    if not min_version:
        errors.append("📦 **min_version**: Required field is missing")
    else:
        try:
            if not os.path.isdir("ultralytics"):
                subprocess.run(
                    ["git", "clone", "https://github.com/ultralytics/ultralytics"],
                    check=True,
                )
            else:
                print("ultralytics directory already exists. Skipping clone.")
            os.chdir("ultralytics")
            subprocess.run(["git", "checkout", f"tags/v{min_version}"], check=True)
            subprocess.run(["pip", "uninstall", "ultralytics", "-y"], check=True)
            subprocess.run(["pip", "install", "."], check=True)
        except subprocess.CalledProcessError:
            errors.append(f"📦 **min_version**: Invalid version `{min_version}`")

    # Validate model, FLOPs, parameters, and strides
    try:
        from ultralytics import YOLO

        model = None
        scales = config.get("scales", [])
        # either one pass or multi-pass per scale:
        if len(scales) <= 1:
            # single-value case
            model = YOLO(file_path)
            _, params, _, flops = model.info()

            if abs(flops - config.get("flops", 0)) > 0.1:
                errors.append(
                    f"💻 **FLOPs**: Expected `{flops:.1f}`, got `{config.get('flops')}`"
                )
            if params != config.get("parameters", 0):
                errors.append(
                    f"🔢 **Parameters**: Expected `{params}`, got `{config.get('parameters')}`"
                )
        else:
            # multi-scale case: expect config["flops"] and config["parameters"] to be dicts
            flops_config = config.get("flops", {})
            params_config = config.get("parameters", {})
            if not isinstance(flops_config, dict):
                errors.append(
                    "⚠️ *Invalid `flops` metadata:* Expected `flops` value for each scale."
                )
                flops_config = {}
            if not isinstance(params_config, dict):
                errors.append(
                    "⚠️ *Invalid `parameters` metadata:* Expected `parameters` value for each scale."
                )
                params_config = {}
            for s in scales.keys():
                # build a filename that YOLO will interpret as that scale
                fp = insert_scale_letter(file_path, s)
                try:
                    model = YOLO(fp)
                    _, params, _, flops = model.info()
                except Exception:
                    errors.append(
                        f"⚠️ Failed to load model with scale `{s}`. Valid scales are `['n', 's', 'm', 'l', 'x']`."
                    )
                    continue

                # compare
                config_flops = flops_config.get(s)
                if config_flops is None or round(flops, 1) - config_flops:
                    errors.append(
                        f"💻 **FLOPs[{s}]**: Expected `{flops:.1f}`, got `{config_flops}`"
                    )

                config_params = params_config.get(s)
                if config_params is None or params != config_params:
                    errors.append(
                        f"🔢 **Parameters[{s}]**: Expected `{config_params}`, got `{params}`"
                    )

        # Validate strides
        if model is not None:
            import torch

            head = model.model.model[-1]
            f, i = head.f, head.i
            head = torch.nn.Identity()
            head.f, head.i = f, i
            model.model.model[-1] = head
            imgsz = 640
            out = model.model(torch.randn(1, 3, imgsz, imgsz))
            computed_strides = [imgsz // o.shape[-1] for o in out]

            if computed_strides != config.get("strides", []):
                errors.append(
                    f"📏 **Strides**: Expected `{computed_strides}`, got `{config.get('strides')}`"
                )
    except Exception as e:
        print(traceback.format_exc())
        errors.append(
            f"⚠️ **Model Error**: Failed to load model with min_version {min_version}: `{str(e)}`"
        )

    # Validate nc
    nc = config.get("nc", 0)
    if not isinstance(nc, int) or nc <= 0:
        errors.append("🎯 **nc**: Must be an integer greater than 0")

    os.chdir("..")
    if errors:
        comment_on_pr(
            f"## ❌ `{folder_name}/{filename}` Validation Failed\n\n"
            + "\n".join(errors)
        )
        return -1
    return 0


def main():
    yaml_files = [
        file
        for file in os.getenv("CFG_ALL_CHANGED_FILES").split()
        if file.endswith((".yaml", ".yml"))
    ]
    if len(yaml_files) > 1:
        comment_on_pr(
            "## ❌ Too Many YAML Files\n\nEach PR should only modify one YAML config file."
        )
        sys.exit(1)
    elif yaml_files:
        return_code = 0
        for file in yaml_files:
            return_code += validate_yaml(os.path.abspath(file))
        if return_code != 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
