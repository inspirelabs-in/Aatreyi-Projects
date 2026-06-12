import argparse
import asyncio
import sys

from app.ai.prompt_runner import run_prompt
from app.cli.register import register_channel, unregister_channel, list_registered_channels
from app.orchestration import run_analysis_pipeline, run_registered_channel_analysis
from app.scheduler.jobs import run_scheduler_once, start_scheduler
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Telegram Growth Agent: register channels and run scheduled collection"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_parser = subparsers.add_parser("register", help="Register a Telegram channel for scheduled collection")
    register_parser.add_argument("--channel", "-c", required=True, help="Channel username, e.g. @grabonindia")
    register_parser.add_argument("--alias", "-a", required=False, help="Optional alias for the channel")

    unregister_parser = subparsers.add_parser("unregister", help="Deactivate a registered channel")
    unregister_parser.add_argument("--channel", "-c", required=True, help="Channel username to deactivate")

    subparsers.add_parser("list", help="List registered channels")
    subparsers.add_parser("run-once", help="Run collection once for all registered channels")
    subparsers.add_parser("schedule", help="Start the scheduler loop")

    analyze_parser = subparsers.add_parser("analyze", help="Run the AI analysis pipeline for a single channel")
    analyze_parser.add_argument("--channel", "-c", required=True, help="Channel username, e.g. @grabonindia")
    analyze_parser.add_argument("--goal", "-g", required=False, help="Operator stated goal")

    subparsers.add_parser("analyze-registered", help="Run the AI analysis pipeline for all registered channels")

    return parser


async def main_async(args: argparse.Namespace) -> int:
    if args.command == "register":
        channel = args.channel.strip()
        if not channel.startswith("@"):
            channel = "@" + channel
        result = await register_channel(channel, args.alias)
        print("Registered channel:", result)

    elif args.command == "unregister":
        channel = args.channel.strip()
        if not channel.startswith("@"):
            channel = "@" + channel
        result = await unregister_channel(channel)
        print("Unregistered:" if result else "Channel not found")

    elif args.command == "list":
        channels = await list_registered_channels()
        if not channels:
            print("No channels registered")
            return 0

        for item in channels:
            print(
                f"{item['id']} - {item['channel_username']}"
                f" ({'active' if item['active'] else 'inactive'})"
                f" alias={item.get('alias', '')} last_run_at={item.get('last_run_at')}"
            )

    elif args.command == "run-once":
        results = await run_scheduler_once()
        print(f"Run once completed for {len(results)} channel(s)")
        for result in results:
            print(f"- {result['channel_username']}: {result['subscriber_count']} subscribers")

    elif args.command == "analyze":
        channel = args.channel.strip()
        if not channel.startswith("@"):
            channel = "@" + channel
        result = await run_analysis_pipeline(channel, args.goal)
        print(f"Analysis complete for {channel}")
        print(result)

    elif args.command == "analyze-registered":
        results = await run_registered_channel_analysis()
        print(f"Analysis complete for {len(results)} registered channel(s)")

    elif args.command == "schedule":
        print("Starting scheduler. Press Ctrl+C to stop.")
        await start_scheduler()

    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        logger.info("Execution interrupted by user")
        return 0
    except Exception as exc:
        logger.error("Unhandled error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
