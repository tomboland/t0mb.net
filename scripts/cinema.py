#!/usr/bin/env python3
"""Entry point for the cinema application; operations live in cinema_service."""
from cinema_data import ROOT as PROJECT_ROOT
import cinema_app

ROOT = PROJECT_ROOT / 'cinema'


def main():
    cinema_app.main(root=ROOT.parent)


if __name__ == '__main__':
    main()
