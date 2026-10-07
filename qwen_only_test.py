import asyncio
import json

from bisnu_x.model.config import ModelConfig
from bisnu_x.reasoning.brain import BISNUBrain


async def main():

    config = ModelConfig.from_env()

    print("")
    print("============================================================")
    print("BISNU-X QWEN ONLY GENERATION TEST")
    print("============================================================")
    print("CONFIGURED MODELS:", end=" ")

    brain = BISNUBrain(config)

    print(brain.models.configured_models())

    messages = [
        {
            "role": "system",
            "content": (
                "You are BISNU-X, an Indian AI research assistant. "
                "Answer briefly and clearly."
            ),
        },
        {
            "role": "user",
            "content": (
                "Namaste BISNU-X. "
                "Apna naam aur current model architecture "
                "short mein batao."
            ),
        },
    ]

    print("")
    print("Sending request to Qwen...")
    print("")

    result = await brain.chat(messages)

    print("")
    print("============================================================")
    print("BISNU-X ANSWER")
    print("============================================================")
    print(result.get("answer", ""))

    print("")
    print("============================================================")
    print("MODEL RESULTS")
    print("============================================================")

    for item in result.get("models", []):
        print(
            "MODEL:",
            item.get("model"),
            "| SUCCESS:",
            item.get("success"),
        )

        if item.get("error"):
            print("ERROR:", item.get("error"))

    print("")
    print("SUCCESSFUL MODELS:", result.get("successful_models"))
    print("FAILED MODELS:", result.get("failed_models"))

    print("")
    print("============================================================")
    print("VERIFICATION")
    print("============================================================")

    print(
        json.dumps(
            result.get("verification", {}),
            indent=2,
            default=str,
        )
    )

    print("")
    print("============================================================")
    print("QWEN GENERATION TEST FINISHED")
    print("============================================================")


asyncio.run(main())
