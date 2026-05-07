# __init__.py
"""Fetches clinic updates across a specified region from a target website."""

from importlib.metadata import version

__all__ = ['run']
__version__ = version('clinictracker')
__author__ = 'Lydia Zhang'

from clinictracker.core import run
