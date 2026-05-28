import unittest
from contextlib import redirect_stderr
from io import StringIO

from benchmarks._harness import parse_args


class BenchmarkHarnessTests(unittest.TestCase):
    def test_parse_args_honors_iterations_and_rounds(self) -> None:
        args = parse_args(['--iterations', '10', '--rounds', '2'])

        self.assertEqual(args.iterations, 10)
        self.assertEqual(args.rounds, 2)

    def test_parse_args_rejects_non_positive_iterations(self) -> None:
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            parse_args(['--iterations', '0'])


if __name__ == '__main__':
    unittest.main()
