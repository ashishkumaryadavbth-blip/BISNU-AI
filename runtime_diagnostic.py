from __future__ import annotations

import json

from bisnu_x.model.config import ModelConfig
from bisnu_x.model.multi_model import MultiModelEngine
from bisnu_x.runtime.compat import runtime_status


def main():

    config = ModelConfig.from_env()
    engine = MultiModelEngine(config)

    print("")
    print("=" * 60)
    print("BISNU-X WEB RUNTIME DIAGNOSTIC")
    print("=" * 60)

    print("")
    print("RUNTIME:")
    print(json.dumps(runtime_status(), indent=2, default=str))

    print("")
    print("CONFIGURED MODELS:")
    print(engine.configured_models())

    print("")
    print("MODEL HEALTH:")
    print(json.dumps(engine.health(), indent=2, default=str))

    print("")
    print("=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
