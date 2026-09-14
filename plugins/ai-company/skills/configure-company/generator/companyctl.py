#!/usr/bin/env python3
"""companyctl — AI 회사 생성기의 결정적 엔진.
정본은 <root>/직원명부.json 하나. 지침 파일은 마커 블록만 추가·제거하고 SESSION.md는 없을 때만 만든다.
비밀값은 읽지도 쓰지도 않는다. 표준 라이브러리만 쓴다.
"""
import argparse
import sys


def main() -> None:
    p = argparse.ArgumentParser(prog="companyctl", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, help_ in [("init", "회사 루트·직원명부 생성"), ("dept", "부서 추가/제거"), ("employee", "직원 등록/제거"),
                        ("install", "폴더·템플릿·지침 블록 설치"), ("remove", "지침 블록 제거(기록 보존)"),
                        ("doctor", "읽기 전용 점검"), ("list", "직원명부 출력")]:
        sub.add_parser(name, help=help_)
    a = p.parse_args()
    print("아직 구현되지 않은 명령:", a.cmd, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
