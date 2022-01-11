import argparse
import svg_to_usd.convert as convert
import logging

parser = argparse.ArgumentParser(description='Convert SVG to USD')
parser.add_argument('input', type=str, help='Path to SVG input file')
parser.add_argument('output', type=str, help='Path for USD output file')

args = parser.parse_args()

_input = args.input
_output = args.output

logging.basicConfig(format='%(levelname)s:\t%(message)s', level=logging.DEBUG)
logging.info("Converting SVG to USD")
logging.info(f" - input: {_input}")
logging.info(f" - output: {_output}")

convert.convert(_input, _output)
