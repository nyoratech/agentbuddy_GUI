import rxconfig
import reflex as rx
#from reflex.vars import Var
#from reflex import Component
from typing import Any, Dict, List, Union


# class textWriting(Component):
#     library = "typewriter-effect"
#     tag = "Typewriter"
#     strings: rx.Var[List[str]] #"Hello World" #, "Hello World")
#     autoStart: rx.Var[bool]# True
#     loop: rx.Var[bool]

    #is_default = True


#type_writer = textWriting.create

class textWriting(rx.Component):
    library = "wc-typeit"
    tag = "Loop"
    #is_default = True
    sentences: rx.Var[List[str]]
    loop: rx.Var[str]


class TextTyper(rx.Component):
    """Color picker component."""

    library = "windups"
    tag = "useWindup"
    is_default = True

class TextWriter(rx.Component):
    """Color picker component."""

    library = "react-type-animation"
    tag = "TypeAnimation "
    sequence: rx.Var[List[Any]]
    #style: rx.Var[Dict[str, str]]
    wrapper: rx.Var[str]
class Spline(rx.Component):
    """Spline component."""

    # The name of the npm package.
    library = "@splinetool/react-spline"

    # Any additional libraries needed to use the component.
    lib_dependencies: list[str] = [
        "@splinetool/runtime@1.5.5"
    ]

    # The name of the component to use from the package.
    tag = "Spline"

    # Spline is a default export from the module.
    is_default = True

    # Any props that the component takes.
    scene: rx.Var[str]


# Convenience function to create the Spline component.
spline = Spline.create

type_writer = TextWriter.create
#def type_writer_component(strings):
#    return type_writer(strings)
