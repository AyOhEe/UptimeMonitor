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
        help="How often, in milliseconds, to ping the target"
    )
    args = parser.parse_args()


    uptime.LOGGER.log(100, f"Beginning to monitor {args.target} every {args.period}ms")
    uptime.start_monitor(args.target, args.period)