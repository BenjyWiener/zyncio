"""Custom hatchling build hook."""

from pathlib import Path
import subprocess

from hatchling.metadata.plugin.interface import MetadataHookInterface


def get_git_ref() -> str:
    """Return the current git tag, or fall back to HEAD commit SHA."""
    try:
        return subprocess.check_output(
            ['git', 'describe', '--tags', '--exact-match'],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        # Not on a tag, fall back to the commit SHA
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()


class MetadataHook(MetadataHookInterface):
    """Custom metadata hook."""

    def update(self, metadata: dict) -> None:
        """Update metadata."""
        # Replace relative logo path with absolute URL.
        readme_text = Path(self.root, 'README.md').read_text()
        logo, readme_text = readme_text.split('\n', 1)
        # Make sure the logo is where we expect it to be.
        assert logo == '![ZyncIO](docs/_static/ZyncIO.png)'
        readme_text = (
            f'![ZyncIO](https://raw.githubusercontent.com/BenjyWiener/zyncio/{get_git_ref()}/docs/_static/ZyncIO.png)\n'
            + readme_text
        )
        metadata['readme'] = {'text': readme_text, 'content-type': 'text/markdown'}
