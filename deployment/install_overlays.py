"""Install the repository overlays into the active Python environment."""

import argparse
import ast
import importlib.util
import json
from pathlib import Path
import shutil
import sysconfig

NEW_MODULES = {"web_search_engines/engines/search_engine_europepmc.py"}
UI_ASSETS = {"web/static/js/astro-subscription-simple.js", "web/static/js/astro-research-simple.js", "web/templates/auth/accounts.html", "web/templates/auth/forbidden.html", "web/static/js/astro-i18n.js", "web/static/js/astro-locale-zh.js", "web/static/css/astro-workspace.css", "web/static/js/astro-workspace.js"}
UI_TARGETS = UI_ASSETS | {
    "web/templates/pages/news-subscription-form.html", "web/templates/pages/news.html", "web/static/js/pages/news.js",
    "web/static/js/mobile-navigation.js",
    "web/templates/pages/chat.html",
    "web/static/js/components/chat.js",
    "web/templates/auth/change_password.html", "web/templates/settings_dashboard.html",
    'web/static/js/components/logpanel.js', 'web/static/js/services/socket.js', 'web/static/js/components/progress.js', 'web/static/js/components/settings.js',
    "web/static/js/services/theme.js",
    "web/templates/base.html", "web/templates/components/sidebar.html",
    "web/templates/pages/research.html", "web/templates/pages/progress.html",
    "web/templates/pages/results.html", "web/templates/pages/history.html",
    "web/templates/auth/login.html", "web/templates/auth/register.html",
}
SEARCH_MODULES = NEW_MODULES | {
    "web_search_engines/engines/search_engine_pubmed.py",
    "web_search_engines/search_engines_config.py",
    "web_search_engines/engine_registry.py", "security/module_whitelist.py",
    "web_search_engines/relevance_filter.py",
}
COLLECTION_TARGET = "advanced_search_system/strategies/langgraph_agent_strategy.py"
COLLECTION_HOOK = '''

# Source collection feedback and stable-identifier deduplication.
from research_verify.source_collection import SourceCollectionMixin, format_collection_results

class SearchResultsCollector(SourceCollectionMixin, SearchResultsCollector):
    pass

_original_collection_formatter = _format_results
def _format_results(results, start_idx):
    return format_collection_results(results, start_idx, _original_collection_formatter)
'''


def reasoning_provider_patch(package):
    """Patch the installed provider's two model factories, retaining its other behavior."""
    target = package / "llm/providers/openai_base.py"
    source = target.read_text(encoding="utf-8")
    old = "        return ChatOpenAI(**llm_params)"
    hook = ('        if cls.provider_key == "OPENAI_ENDPOINT":\n'
            '            from research_verify.reasoning_transport import create_capture_model\n'
            '            return create_capture_model(llm_params, settings_snapshot)\n' + old)
    if source.count(hook) == 2:
        return None
    if source.count(old) != 2 or hook in source:
        raise ValueError(f"Incompatible OpenAI-compatible provider factory: {target}")
    content = source.replace(old, hook)
    ast.parse(content, filename=str(target))
    return target, content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--search-only", action="store_true",
                        help="Install only retrieval.py from research_verify")
    mode.add_argument("--collection-only", action="store_true",
                      help="Install search modules plus source collection corrections")
    mode.add_argument("--ui-only", action="store_true",
                      help="Install only templates and workspace assets; leave backend modules unchanged")
    args = parser.parse_args()
    spec = importlib.util.find_spec("local_deep_research")
    if spec is None or not spec.submodule_search_locations:
        parser.error("local_deep_research must be installed first")
    package = Path(next(iter(spec.submodule_search_locations)))
    verify_source = args.source / "research_verify"
    verify_target = Path(sysconfig.get_path("purelib")) / "research_verify"
    patch = None
    if not any((args.ui_only, args.search_only, args.collection_only)) and (verify_source / "reasoning_transport.py").is_file():
        patch = reasoning_provider_patch(package)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    restricted = args.search_only or args.collection_only
    if restricted and set(manifest.values()) - SEARCH_MODULES:
        parser.error("search-only manifest contains modules outside retrieval")
    if args.ui_only and set(manifest.values()) - UI_TARGETS:
        parser.error("ui-only manifest contains modules outside the workspace UI")
    # Validate every source and target before changing the installed package.
    for source, target in manifest.items():
        content = (args.source / source).read_text(encoding="utf-8")
        if Path(source).suffix == ".py":
            ast.parse(content, filename=source)
        elif Path(source).suffix == ".html":
            from jinja2 import Environment
            Environment().parse(content)
        elif Path(source).suffix not in {".js", ".css"}:
            parser.error(f"unsupported overlay type: {source}")
        if not (package / target).is_file() and target not in NEW_MODULES | UI_ASSETS:
            parser.error(f"incompatible base image: missing {target}")
    if args.ui_only:
        for source, target in manifest.items():
            shutil.copy2(args.source / source, package / target)
            print(f"ui overlay: {source} -> {target}")
        return
    defaults_path = package / "defaults/default_settings.json"
    search_defaults = args.source / "search_defaults.json"
    defaults = None
    if search_defaults.is_file():
        defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
        for key, value in json.loads(search_defaults.read_text(encoding="utf-8")).items():
            if not key.startswith("search."):
                parser.error(f"invalid search default: {key}")
            if key in defaults:
                defaults[key]["value"] = value
            else:
                defaults[key] = {
                    "category": key.split(".")[3] if key.startswith("search.engine.web.") else "search",
                    "name": key.rsplit(".", 1)[-1],
                    "description": "Search retrieval configuration", "type": "SEARCH",
                    "ui_element": "checkbox" if isinstance(value, bool) else "text",
                    "editable": True, "visible": True, "value": value,
                }
        options = defaults["search.tool"].get("options") or []
        if not any(option["value"] == "europepmc" for option in options):
            options.append({"label": "Europe PMC", "value": "europepmc"})
        defaults["search.tool"]["options"] = options
    if restricted and not (verify_target / "__init__.py").is_file():
        parser.error("search-only installation requires existing research_verify package")
    package_files = ["retrieval.py"] + (["source_collection.py"] if args.collection_only else [])
    verify_files = [verify_source / n for n in package_files] if restricted else verify_source.rglob("*.py")
    for source in verify_files:
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    collection_target = package / COLLECTION_TARGET
    if not args.search_only and (verify_source / "source_collection.py").is_file():
        original = collection_target.read_text(encoding="utf-8")
        replacement = next((args.source / s for s, t in manifest.items() if t == COLLECTION_TARGET), None)
        candidate = replacement.read_text(encoding="utf-8") if replacement else original
        ast.parse(candidate + COLLECTION_HOOK, filename=COLLECTION_TARGET)
    for source, target in manifest.items():
        shutil.copy2(args.source / source, package / target)
        print(f"overlay: {source} -> {target}")
    if defaults is not None:
        defaults_path.write_text(json.dumps(defaults, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    if restricted:
        for name in package_files:
            shutil.copy2(verify_source / name, verify_target / name)
    else:
        shutil.copytree(verify_source, verify_target, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if patch:
        patch[0].write_text(patch[1], encoding="utf-8")
    if not args.search_only and (verify_source / "source_collection.py").is_file():
        installed = collection_target.read_text(encoding="utf-8")
        if "# Source collection feedback and stable-identifier deduplication." not in installed:
            collection_target.write_text(installed + COLLECTION_HOOK, encoding="utf-8")


if __name__ == "__main__":
    main()
