from datapack.datapack import Datapack
from typing_extensions import override

OUTPUT_ROOT = "data/minecraft/loot_tables"
INPUT_ROOT = "resources/luck"

class LuckGranter(Datapack):
    def __init__(self):
        from os import walk
        from os.path import isdir, relpath, join

        if not isdir(INPUT_ROOT):
            raise RuntimeError("Luck datapack utilities don't exist.")

        self.input_files: set[str] = set()

        for dir_, _, files in walk(INPUT_ROOT):
            for file_name in files:
                rel_dir = relpath(dir_, INPUT_ROOT)
                if file_name == 'blaze.json':
                    continue
                self.input_files.add(join(rel_dir, file_name))

        self.file_data = {
            join(OUTPUT_ROOT, k): open(join(INPUT_ROOT, k)).read() for k in self.input_files
        }

    @override
    def custom_file(self) -> dict[str, str]:
        return self.file_data
