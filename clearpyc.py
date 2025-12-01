import os
import shutil

def clean_pycache_folders(directory):
    for root, dirs, files in os.walk(directory):
        for dir_name in dirs:
            if dir_name == '__pycache__':
                dir_path = os.path.join(root, dir_name)
                shutil.rmtree(dir_path)
                print(f"Deleted: {dir_path}")

if __name__ == "__main__":
    current_directory = os.getcwd()
    clean_pycache_folders(current_directory)