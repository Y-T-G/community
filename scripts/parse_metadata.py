import yaml
import sys
import os

def main(yaml_file):
    try:
        folder = os.path.basename(os.path.dirname(yaml_file))
        filename = os.path.basename(yaml_file)
        discussion_title = f"{folder}/{filename}"

        with open(yaml_file, 'r') as f:
            config = yaml.safe_load(f)

        metadata_keys = ['author', 'task', 'keywords', 'description', 'flops', 'parameters', 'min_version']
        metadata = {k: v for k, v in config.items() if k in metadata_keys}

        emoji_map = {
            'author': '👤',
            'task': '🎯',
            'keywords': '🔑',
            'description': '📝',
            'flops': '⚡',
            'parameters': '🔢',
            'min_version': '💻'
        }

        body = f"# Discussion for `{discussion_title}`\n\n## 📊 Metadata\n"
        for key, value in metadata.items():
            emoji = emoji_map.get(key, '')
            if key == 'author':
                value = f"**@{value}**"
            elif key == 'keywords':
                value = ', '.join(f'`{k}`' for k in value) if isinstance(value, list) else f'`{value}`'
            body += f"{emoji} **{key}:** {value}\n"

        with open('discussion_body.txt', 'w') as f:
            f.write(body)

    except Exception as e:
        print(f"Error processing YAML file {yaml_file}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/parse_metadata.py <path_to_yaml_file>")
        sys.exit(1)
    yaml_file = sys.argv[1]
    main(yaml_file)