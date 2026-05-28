"""Utility script for running the typing test suite."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory


TESTS_PATH = Path(__file__).parent / 'tests'
TYPE_CHECKER_CONFIGS = TESTS_PATH / 'type-checker-configs'
PYPROJECT_PATH = Path(__file__).parent / 'pyproject.toml'
EXCLUSIONARY_IGNORE_RE = re.compile(r'# type: ignore\[(x-\w+(?:,x-\w+)*)\](?=$|\s*#)', flags=re.MULTILINE)
TYPE_IGNORE_RE = re.compile(r'# type: ignore(?=$|\s*#)', flags=re.MULTILINE)


@dataclass
class TypeChecker:
    """A type checker configuration for running the typing tests."""

    name: str
    """The name of the type checker."""

    build_command: Callable[[str], Sequence[str | Path]]
    """Build command line for executing the type checker for the given path."""

    config_file: str | None = None
    """Name of optional configuration file to copy to the parent directory."""

    ignore_comment: str | None = None
    """Optional checker-specific ignore comment (should trigger "unnecessary type ignore" if supported).

    This should be used for type checkers that only report their own unused ignore comments, and not generic
    `type: ignore`.
    """

    fake_ignore_comment: str | None = None
    """Optional checker-specfic ignore comment that should be replaced with a standard `type: ignore`.

    This is primarly for supporting Mypy-specific ignore, since Mypy doesn't currently support `mypy: ignore`-style
    comments.
    """

    def check(self) -> bool:
        """Run the typing tests with this type checker.

        :return: `True` if the tests passed without any unexpected type errors, `False` otherwise.
        """
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / TESTS_PATH.name
            for file in TESTS_PATH.glob('**/*.py'):
                dest = temp_path / file.relative_to(TESTS_PATH)
                dest.parent.mkdir(parents=True, exist_ok=True)

                content = file.read_text()

                content = EXCLUSIONARY_IGNORE_RE.sub(self._handle_exclusionary_ignore, content)

                if self.ignore_comment:
                    content = TYPE_IGNORE_RE.sub(f'# {self.ignore_comment}', content)

                if self.fake_ignore_comment:
                    content = re.sub(
                        rf'# {re.escape(self.fake_ignore_comment)}(?=$|\s*#)',
                        '# type: ignore',
                        content,
                        flags=re.MULTILINE,
                    )

                dest.write_text(content)

            if self.config_file:
                (TYPE_CHECKER_CONFIGS / self.config_file).copy(temp_path.parent / self.config_file)

            command = self.build_command(temp_path.name)

            print('* Temp dir:', temp_path)
            print('* Command:', command)

            result = subprocess.run(command, cwd=temp_path.parent)

        return result.returncode == 0

    def _handle_exclusionary_ignore(self, match: re.Match[str]) -> str:
        """Handle our custom `type: ignore[x-checker1,x-checker2]` comments."""
        excluded = match.group(1).split(',')
        return '' if f'x-{self.name.lower()}' in excluded else '# type: ignore'


TYPE_CHECKERS = [
    TypeChecker(
        name='Mypy',
        build_command=lambda path: ['mypy', '--', path],
        fake_ignore_comment='mypy: ignore',
        config_file='mypy.ini',
    ),
    TypeChecker(
        name='Pyrefly',
        build_command=lambda path: ['pyrefly', 'check', '--', path],
        ignore_comment='pyrefly: ignore',
        config_file='pyrefly.toml',
    ),
    TypeChecker(
        name='Pyright',
        build_command=lambda path: ['pyright', '--stats', path],
        config_file='pyrightconfig.json',
    ),
    TypeChecker(
        name='ty',
        build_command=lambda path: ['ty', 'check', '--', path],
        ignore_comment='ty: ignore',
    ),
    TypeChecker(
        name='Zuban',
        build_command=lambda path: ['zuban', 'check', '--', path],
        ignore_comment='zuban: ignore',
    ),
]

match sys.argv[1:]:
    case [str(name)]:
        checker = next(c for c in TYPE_CHECKERS if c.name.lower() == name.lower())
        print(f'Running typing tests with {checker.name}...')
        if checker.check():
            print('Tests passed.')
            sys.exit(0)
        else:
            print('Tests failed. Examine output for details.')
            sys.exit(1)
    case _:
        print(f'Usage: {sys.argv[0]} <type checker>')
        print('Available type checkers:')
        for checker in TYPE_CHECKERS:
            print(f'  - {checker.name}')
        sys.exit(2)
