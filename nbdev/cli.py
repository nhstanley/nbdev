# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/12_cli.ipynb.

# %% ../nbs/12_cli.ipynb 1
from __future__ import annotations
import warnings

from .config import *
from .process import *
from .processors import *
from .doclinks import *
from .test import *
from .clean import *
from .quarto import refresh_quarto_yml

from execnb.nbio import *
from fastcore.utils import *
from fastcore.script import call_parse
from fastcore.style import S
from fastcore.shutil import rmtree,move

from urllib.error import HTTPError
from contextlib import redirect_stdout
import os, tarfile, sys

# %% auto 0
__all__ = ['prepare', 'FilterDefaults', 'nbdev_filter', 'extract_tgz', 'prompt_user', 'nbdev_new', 'chelp']

# %% ../nbs/12_cli.ipynb 6
@call_parse
def prepare():
    "Export, test, and clean notebooks"
    nbdev_export.__wrapped__()
    nbdev_test.__wrapped__()
    nbdev_clean.__wrapped__()

# %% ../nbs/12_cli.ipynb 8
class FilterDefaults:
    "Override `FilterDefaults` to change which notebook processors are used"
    def xtra_procs(self): return []

    def base_procs(self):
        return [populate_language, infer_frontmatter, add_show_docs, insert_warning,
                strip_ansi, hide_line, filter_stream_, rm_header_dash,
                clean_show_doc, exec_show_docs, rm_export, clean_magics, hide_, add_links, strip_hidden_metadata]

    def procs(self):
        "Processors for export"
        return self.base_procs() + self.xtra_procs()
    
    def nb_proc(self, nb):
        "Get an `NBProcessor` with these processors"
        return NBProcessor(nb=nb, procs=self.procs())

# %% ../nbs/12_cli.ipynb 9
@call_parse
def nbdev_filter(
    nb_txt:str=None,  # Notebook text (uses stdin if not provided)
    fname:str=None,  # Notebook to read (uses `nb_txt` if not provided)
):
    "A notebook filter for Quarto"
    os.environ["IN_TEST"] = "1"
    try: filt = get_config().get('exporter', FilterDefaults)()
    except FileNotFoundError: filt = FilterDefaults()
    printit = False
    if fname: nb_txt = Path(fname).read_text()
    elif not nb_txt: nb_txt,printit = sys.stdin.read(),True
    nb = dict2nb(loads(nb_txt))
    if printit:
        with open(os.devnull, 'w') as dn:
            with redirect_stdout(dn): filt.nb_proc(nb).process()
    else: filt.nb_proc(nb).process()
    res = nb2str(nb)
    del os.environ["IN_TEST"]
    if printit: print(res, flush=True)
    else: return res

# %% ../nbs/12_cli.ipynb 12
def extract_tgz(url, dest='.'):
    from fastcore.net import urlopen
    with urlopen(url) as u: tarfile.open(mode='r:gz', fileobj=u).extractall(dest)

# %% ../nbs/12_cli.ipynb 13
def _mk_cfg(**kwargs): return {k: kwargs.get(k,None) for k in 'lib_name user branch author author_email keywords description repo'.split()}

# %% ../nbs/12_cli.ipynb 14
def _get_info(owner, repo, default_branch='main', default_kw='nbdev'):
    from ghapi.all import GhApi
    api = GhApi(owner=owner, repo=repo, token=os.getenv('GITHUB_TOKEN'))
    
    try: r = api.repos.get()
    except HTTPError:
        msg= [f"""Could not access repo: {owner}/{repo} to find your default branch - `{default_branch} assumed.
Edit `settings.ini` if this is incorrect.
In the future, you can allow nbdev to see private repos by setting the environment variable GITHUB_TOKEN as described here:
https://nbdev.fast.ai/cli.html#Using-nbdev_new-with-private-repos
"""]
        print(''.join(msg))
        return (default_branch,default_kw,'')
    
    return r.default_branch, default_kw if not r.topics else ' '.join(r.topics), r.description

# %% ../nbs/12_cli.ipynb 16
def _fetch_from_git(raise_err=False):
    "Get information for settings.ini from the user."
    res={}
    try:
        url = run('git config --get remote.origin.url')
        res['user'],res['repo'] = repo_details(url)
        res['branch'],res['keywords'],desc = _get_info(owner=res['user'], repo=res['repo'])
        if desc: res['description'] = desc
        res['author'] = run('git config --get user.name').strip() # below two lines attempt to pull from global user config
        res['author_email'] = run('git config --get user.email').strip()
    except OSError as e:
        if raise_err: raise(e)
    else: res['lib_name'] = res['repo'].replace('-','_')
    return res

# %% ../nbs/12_cli.ipynb 18
def prompt_user(cfg, inferred):
    "Let user input values not in `cfg` or `inferred`."
    print(S.dark_gray('# settings.ini'))
    res = cfg.copy()
    for k,v in cfg.items():
        inf = inferred.get(k,None)
        msg = S.light_blue(k) + ' = '
        if v is None:
            if inf is None: res[k] = input(f'# Please enter a value for {k}\n'+msg)
            else:
                res[k] = inf
                print(msg+res[k]+' # Automatically inferred from git')
        else: print(msg+str(v))
    return res

# %% ../nbs/12_cli.ipynb 19
def _render_nb(fn, cfg):
    "Render templated values like `{{lib_name}}` in notebook at `fn` from `cfg`"
    txt = fn.read_text()
    txt = txt.replace('from your_lib.core', f'from {cfg.lib_path}.core') # for compatibility with old templates
    for k,v in cfg.d.items(): txt = txt.replace('{{'+k+'}}', v)
    fn.write_text(txt)

# %% ../nbs/12_cli.ipynb 20
@call_parse
def nbdev_new(lib_name: str=None): # Package name (default: inferred from repo name)
    "Create a new project."
    from fastcore.net import urljson

    path = Path()
    tag = urljson('https://api.github.com/repos/fastai/nbdev-template/releases/latest')['tag_name']
    url = f"https://github.com/fastai/nbdev-template/archive/{tag}.tar.gz"
    extract_tgz(url)
    tmpl_path = path/f'nbdev-template-{tag}'

    defaults = _mk_cfg(lib_name=lib_name)
    inferred = _fetch_from_git()
    user_cfg = prompt_user(defaults, inferred)
    tmpl_cfg = Path(tmpl_path/'settings.ini').read_text().format(**user_cfg)
    Path('settings.ini').write_text(tmpl_cfg)
    cfg = get_config()

    nbexists = bool(first(path.glob('*.ipynb')))
    for o in tmpl_path.ls():
        if o.name == 'index.ipynb': _render_nb(o, cfg)
        if o.name == '00_core.ipynb' and not nbexists: move(str(o), './')
        elif not (path/o.name).exists(): move(str(o), './')
    rmtree(tmpl_path)

    refresh_quarto_yml()

    nbdev_export.__wrapped__()

# %% ../nbs/12_cli.ipynb 36
@call_parse
def chelp():
    "Show help for all console scripts"
    from fastcore.xtras import console_help
    console_help('nbdev')
