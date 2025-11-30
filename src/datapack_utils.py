from draft import Draft, Datapack
from utils import LOG

# Set up our necessary stuff for download / datapack caching
DATAPACK_CACHE_DIR = ".datapacks"
# key: (path, filename)
DATAPACK_CACHE: dict[str, tuple[str, str]] = {
    
}
DATAPACK_SRC = "draaftpack"
DATAPACK_GEN_DIR = ".temp"
def setup_datapack_caching():
    from os import makedirs, listdir, path, getcwd, remove
    full_dir = path.join(getcwd(), DATAPACK_CACHE_DIR)
    if not path.isdir(DATAPACK_CACHE_DIR):
        makedirs(DATAPACK_CACHE_DIR)
        print('Made datapacks directory:', full_dir)
    else:
        packs = [x for x in listdir(full_dir) if path.isfile(path.join(full_dir, x))]
        print('Found pre-existing datapacks directory with', len(packs), 'datapacks')
        print('Removing old datapacks...')
        for p in packs:
            remove(path.join(full_dir, p))

    # .temp should be fully cleared
    if path.isdir(DATAPACK_GEN_DIR):
        import shutil
        shutil.rmtree(DATAPACK_GEN_DIR)
        print('Removed datapacks generation directory:', DATAPACK_GEN_DIR)
    makedirs(DATAPACK_GEN_DIR)

    # require that draaftpack/ is in the right location
    if not path.isdir(DATAPACK_SRC):
        raise RuntimeError(f"Startup failure: {DATAPACK_SRC} is not a directory!")

    if False:
        from draft import DraftPick
        d = Draft(max_picks=1, picks_per_pool=1)
        d.draft.append(DraftPick(key="badlands", player="123", index=1))
        d.draft.append(DraftPick(key="rates", player="123", index=1))
        d.draft.append(DraftPick(key="helmet", player="123", index=1))
        d.draft.append(DraftPick(key="bucket", player="321", index=1))
        d.draft.append(DraftPick(key="axe", player="321", index=1))
        _generate_datapack('fake-pack-id', '123', 'John', d)
        _generate_datapack('fake-pack-id-2', '321', 'Jane', d)


def _apply_datapack(loc: str, username: str, dt: Datapack):
    from os import makedirs
    from os.path import dirname, join
    for fn, val in dt.custom_file().items():
        # make sure we don't have a situation
        assert not fn.startswith('/')
        makedirs(dirname(join(loc, fn)), exist_ok=True)
        with open(join(loc, fn), 'a') as file:
            file.write(val)


def _apply_generic(loc: str, username: str, dts: list[Datapack]):
    from os.path import join
    onload = join(loc, 'data/draaftpack/functions/on_load.mcfunction')
    with open(onload, 'a') as file:
        for dt in dts:
            ol = dt.onload(username)
            if len(ol):
                file.write('\n')
                file.write(ol)
                if not ol.endswith('\n'):
                    file.write('\n')
    ontick = join(loc, 'data/draaftpack/functions/tick.mcfunction')
    with open(ontick, 'a') as file:
        for dt in dts:
            ol = dt.ontick(username)
            if len(ol):
                file.write('\n')
                file.write(ol)
                if not ol.endswith('\n'):
                    file.write('\n')


def _generate_datapack(pack_id: str, uuid: str, username: str, draft: Draft):
    from draft import DATAPACK
    import shutil
    from os.path import join, isdir

    # setup: copy to the source directory
    gen_dir = join(DATAPACK_GEN_DIR, pack_id)
    if isdir(gen_dir):
        # exceptional, remove
        shutil.rmtree(gen_dir)
    shutil.copytree(src=DATAPACK_SRC, dst=gen_dir)

    # draft application: find all the picks for this player
    for pick in draft.draft:
        if pick.player != uuid:
            continue
        if pick.key not in DATAPACK:
            LOG(f'{pick.key} does not have a datapack object!')
            continue
        LOG(f'Applying {pick.key} to player {pick.player}')
        o = DATAPACK[pick.key]
        for dt in o:
            # apply all specific things
            _apply_datapack(gen_dir, username, dt)
        # apply onload & ontick
        _apply_generic(gen_dir, username, o)

    for gb in draft.get_gambits(uuid):
        if gb not in DATAPACK:
            continue
        gambit = DATAPACK[gb]
        for dt in gambit:
            _apply_datapack(gen_dir, username, dt)
        _apply_generic(gen_dir, username, gambit)

    # it's done. now we generate the zip and remove the thing itself
    filename = f'{pack_id}.zip'
    zip_path = join(DATAPACK_CACHE_DIR, pack_id)
    shutil.make_archive(base_name=zip_path, format='zip', root_dir=gen_dir)
    
    # remove the source directory :)
    shutil.rmtree(gen_dir) 

    DATAPACK_CACHE[pack_id] = (zip_path + '.zip', filename)
    

# returns f
def get_datapack(uuid: str, username: str, code: str, draft: Draft):
    pack_id = f'pack_{code}_{uuid}'
    if pack_id not in DATAPACK_CACHE:
        _generate_datapack(pack_id, uuid, username, draft)
    # guaranteed to have the pack here
    return DATAPACK_CACHE[pack_id]
