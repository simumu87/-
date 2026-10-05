from .translator import get_translator, translator_self_test, TRANSLATOR_VERSION


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Krea2 offline Korean-English translator")
    parser.add_argument("--self-test", action="store_true", help="run built-in translation checks")
    parser.add_argument("--stats", action="store_true", help="show loaded dictionary statistics")
    parser.add_argument("text", nargs="*", help="Korean text to translate")
    args = parser.parse_args()
    translator = get_translator()
    print(f"Krea2 Embedded Translator {TRANSLATOR_VERSION}")
    if args.stats:
        print(translator.stats())
    if args.self_test or not args.text:
        for src, ok, got in translator_self_test():
            print(f"{'OK' if ok else 'FAIL'} | {src} -> {got}")
    else:
        print(translator.translate(" ".join(args.text)))


if __name__ == "__main__":
    main()
