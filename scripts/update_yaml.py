import sys
import yaml

def main(yaml_file, discussion_url):
    try:
        # Load all lines to preserve formatting
        with open(yaml_file, "r") as f:
            lines = f.readlines()

        new_lines = []
        min_version_index = None
        discussion_key_found = False
        discussion_line = f"discussion: {discussion_url}\n"

        # Match top-level keys only, so a description mentioning "discussion:" is left alone
        for line in lines:
            if line.startswith("min_version:"):
                min_version_index = len(new_lines)
            if line.startswith("discussion:"):
                new_lines.append(discussion_line)
                discussion_key_found = True
            else:
                new_lines.append(line)

        if not discussion_key_found:
            if min_version_index is not None:
                new_lines.insert(min_version_index + 1, discussion_line)
            else:
                print(f"Warning: min_version not found in {yaml_file}, adding discussion at top")
                new_lines.insert(0, discussion_line)

        with open(yaml_file, "w") as f:
            f.writelines(new_lines)

    except Exception as e:
        print(f"Error updating YAML file {yaml_file}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/update_yaml.py <path_to_yaml_file> <discussion_url>"
        )
        sys.exit(1)
    yaml_file = sys.argv[1]
    discussion_url = sys.argv[2]
    main(yaml_file, discussion_url)
