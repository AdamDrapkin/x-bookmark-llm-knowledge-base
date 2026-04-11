#!/usr/bin/env python3
"""Standalone QA council event trigger."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_core import init_environment, check_and_run_qa_if_needed

def main():
    config = init_environment()
    check_and_run_qa_if_needed(config)

if __name__ == "__main__":
    main()