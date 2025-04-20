import argparse
import uptime

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target", 
        default="8.8.8.8", 
        help="The IP(v4/v6) address to ping when checking WAN accessibility"
    )
    parser.add_argument(
        "--period",
        default=2000,
        type=int,
        help="How often, in milliseconds, to ping the target"
    )
    parser.add_argument(
        "--stdout",
        default=False,
        action="store_true",
        help="Disables output to stdout"
    )
    args = parser.parse_args()


    uptime.start_monitor(args.target, args.period, use_stdout=args.stdout)