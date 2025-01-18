import sys

def main(yaml_file, discussion_url):
    try:
        # Load all lines to preserve formatting
        with open(yaml_file, 'r') as f:
            lines = f.readlines()

        new_lines = []
        min_version_found = False
        for line in lines:
            new_lines.append(line)
            if 'min_version:' in line and not min_version_found:
                # Add the discussion link after min_version
                new_lines.append(f"discussion: {discussion_url}\n")
                min_version_found = True

        with open(yaml_file, 'w') as f:
            f.writelines(new_lines)

    except Exception as e:
        print(f"Error updating YAML file {yaml_file}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/update_yaml.py <path_to_yaml_file> <discussion_url>")
        sys.exit(1)
    yaml_file = sys.argv[1]
    discussion_url = sys.argv[2]
    main(yaml_file, discussion_url)