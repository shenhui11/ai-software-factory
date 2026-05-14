#!/usr/bin/env python3
"""测试运行脚本"""
import subprocess
import sys
import argparse

def run_tests(args):
    """运行测试"""
    cmd = ["pytest"]
    
    if args.test_path:
        cmd.append(args.test_path)
    if args.markers:
        cmd.append(f"-m {args.markers}")
    if args.failed_first:
        cmd.append("--failed-first")
    if args.exitfirst:
        cmd.append("--exitfirst")
    if args.verbose:
        cmd.append("-v")
    
    result = subprocess.run(cmd)
    return result.returncode

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="运行测试")
    parser.add_argument("test_path", nargs="?", help="测试路径")
    parser.add_argument("-m", "--markers", help="运行特定标记的测试")
    parser.add_argument("--failed-first", action="store_true", help="先运行失败的测试")
    parser.add_argument("--exitfirst", action="store_true", help="遇到失败时退出")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    sys.exit(run_tests(args))
