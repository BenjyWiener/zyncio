"""Internal Sphinx extension that patches various parts of autodoc/sphinx-autodoc-typehints."""

from collections.abc import AsyncGenerator, Callable, Coroutine, Generator
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
import inspect
from typing import Any, Concatenate, ParamSpec, ParamSpecArgs, ParamSpecKwargs, TypeIs, TypeVar, get_args, get_origin

from sphinx.application import Sphinx
from sphinx.config import Config
from sphinx.ext.autodoc import Options
import sphinx_autodoc_typehints

import zyncio


@contextmanager
def _cm() -> Generator[None]:
    yield


@asynccontextmanager
async def _acm() -> AsyncGenerator[None]:
    yield


_CM_CODE = _cm.__code__
_ACM_CODE = _acm.__code__


def _before_process_signature(app: Sphinx, obj: object, bound_method: bool) -> None:
    try:
        if inspect.isfunction(obj):
            # Detect wrappers created by `contextlib.contextmanager`` and `contextlib.asynccontextmanager`.
            if obj.__code__ in (_CM_CODE, _ACM_CODE):
                sig = inspect.signature(obj, eval_str=True)
                # Replace `Generator`/`AsyncGenerator` in return annotation with
                # `AbstractContextManager`/`AbstractAsyncContextManager`.
                if get_origin(sig.return_annotation) is Generator:
                    (yield_type,) = get_args(sig.return_annotation)
                    inspect.unwrap(obj).__annotations__['return'] = AbstractContextManager[yield_type]
                elif get_origin(sig.return_annotation) is AsyncGenerator:
                    (yield_type,) = get_args(sig.return_annotation)
                    inspect.unwrap(obj).__annotations__['return'] = AbstractAsyncContextManager[yield_type]
    except Exception:
        pass


def _stringify_type_param(param: TypeVar | ParamSpec) -> str:
    if isinstance(param, TypeVar):
        if param.__bound__:
            return f'{param.__name__}: {param.__bound__}'
        return param.__name__
    elif isinstance(param, ParamSpec):
        return f'**{param.__name__}'


def _process_signature(
    app: Sphinx, obj_type: str, name: str, obj: object, options: Options, signature: str, return_annotation: str
) -> tuple[str, None] | None:
    # Add type parameters to signatures of generic classes.
    if obj_type == 'class' and (type_params := getattr(obj, '__parameters__', None)):
        if processed_sig_ret := sphinx_autodoc_typehints.process_signature(
            app, obj_type, name, obj, options, signature, return_annotation
        ):
            (signature, _) = processed_sig_ret
            type_params_str = ', '.join(map(_stringify_type_param, type_params))
            return f'[{type_params_str}]{signature}', None

    return None


def _should_skip_member(app: Sphinx, obj_type: str, name: str, obj: object, skip: bool, options: object) -> bool | None:
    if name == '__annotations_cache__':
        return True

    return None


def _fix_functionwrapper_init_signatures() -> None:
    for cls in zyncio._ZyncFunctionWrapper.__subclasses__():
        if cls.__init__ is zyncio._ZyncFunctionWrapper.__init__:
            # Create wrapper with more precise annotation for `func`.
            for base in getattr(cls, '__orig_bases__', ()):
                if get_origin(base) is zyncio._ZyncFunctionWrapper:
                    (func_annotation,) = get_args(base)

                    def __init__(self, func):
                        return zyncio._ZyncFunctionWrapper.__init__(self, func)

                    # Setting annotations here is necessary to avoid delayed evaluation issues on Python 3.14+.
                    __init__.__annotations__ = {
                        'func': func_annotation,
                        'return': None,
                    }
                    __init__.__doc__ = zyncio._ZyncFunctionWrapper.__init__.__doc__
                    cls.__init__ = __init__

                    break


def _fix_boundfunctionwrapper_init_signatures() -> None:
    for cls in zyncio._BoundZyncFunctionWrapper.__subclasses__():
        if cls.__init__ is zyncio._BoundZyncFunctionWrapper.__init__:
            # Create wrapper with more precise annotations for `func` and `instance`.
            for base in getattr(cls, '__orig_bases__', ()):
                if get_origin(base) is zyncio._BoundZyncFunctionWrapper:
                    (_mode, instance_annotation, func_annotation) = get_args(base)

                    def __init__(self, func, instance):
                        return zyncio._BoundZyncFunctionWrapper.__init__(self, func, instance)

                    # Setting annotations here is necessary to avoid delayed evaluation issues on Python 3.14+.
                    __init__.__annotations__ = {
                        'func': func_annotation,
                        'instance': instance_annotation,
                        'return': None,
                    }
                    __init__.__doc__ = zyncio._BoundZyncFunctionWrapper.__init__.__doc__
                    cls.__init__ = __init__

                    break


def _process_docstring(app: Sphinx, obj_type: str, name: str, obj: object, options: Options, lines: list[str]) -> None:
    if lines and lines[0].startswith('Alias'):
        # Remove auto-generated rtype from method aliases.
        lines[:] = (line for line in lines if not line.startswith(':rtype:'))

    # Wrap example code blocks in collapsible sections
    for i, line in enumerate(lines):
        if line == 'Example::':
            lines[i : i + 1] = (
                # Use smaller indent so we don't need to reindent the actual code block.
                '.. dropdown:: Example',
                '  :icon: code',
                '  :class-body: sd-p-0',  # Remove padding from inner code block
                '',
                '  .. code-block:: python',
            )


def _typehints_formatter(annotation: object, config: Config) -> str | None:
    """sphinx-autodoc-typehints hook to handle some annotations specially."""
    try:
        if isinstance(annotation, (TypeVar, ParamSpec)):
            return f'`{annotation.__name__}`'

        if isinstance(annotation, ParamSpecArgs):
            return rf'`{annotation.__origin__.__name__}`.\ `~typing.ParamSpec.args`'

        if isinstance(annotation, ParamSpecKwargs):
            return rf'`{annotation.__origin__.__name__}`.\ `~typing.ParamSpec.kwargs`'

        if get_origin(annotation) is Callable:
            params, return_annotation = get_args(annotation)

            if not isinstance(params, list):
                params = [params]

            flat_params = []
            for param in params:
                if get_origin(param) is Concatenate:
                    flat_params.extend(get_args(param))
                else:
                    flat_params.append(param)

            params_strs = []
            for param in flat_params:
                if isinstance(param, ParamSpec):
                    params_strs.append(rf'``*``\ `{param.__name__}`.\ `~typing.ParamSpec.args`')
                    params_strs.append(rf'``**``\ `{param.__name__}`.\ `~typing.ParamSpec.kwargs`')
                else:
                    params_strs.append(sphinx_autodoc_typehints.format_annotation(param, config))
                    import inspect

                    inspect.isgeneratorfunction

            prefix = ''
            if get_origin(return_annotation) is Coroutine:
                _, _, return_annotation = get_args(return_annotation)
                prefix = '``async`` '

            param_str = ', '.join(params_strs)
            return_str = sphinx_autodoc_typehints.format_annotation(return_annotation, config)

            return rf'{prefix}`(`\ {(param_str)}\ `)` -> {return_str}'

        if get_origin(annotation) is TypeIs:
            (inner,) = get_args(annotation)
            return rf'`~typing.TypeIs`\ [{sphinx_autodoc_typehints.format_annotation(inner, config)}]'
    except Exception:
        pass

    return None


def setup(app: Sphinx) -> dict[str, Any]:
    """Set up this extension."""
    # Patch `zyncio`.
    _fix_functionwrapper_init_signatures()
    _fix_boundfunctionwrapper_init_signatures()

    # Connect event hooks.
    app.connect('autodoc-before-process-signature', _before_process_signature)
    app.connect(
        'autodoc-process-signature',
        _process_signature,
        # Must have higher priority than the sphinx-autodoc-typehints hook.
        priority=100,
    )
    app.connect('autodoc-skip-member', _should_skip_member)
    app.connect('autodoc-process-docstring', _process_docstring)

    # Add sphinx-autodoc-typehints hook.
    app.config.typehints_formatter = _typehints_formatter

    return {'version': 1, 'parallel_read_safe': True}
