# Report: 0.5, vocabulary, units, errors

Branch chp/0.5 (from chp/0.4), commits 4bac2cc, 74a52ad (plan docs), 45c2a86.

| Criterion (docs/v1_plan.md) | State |
|---|---|
| old names warn and still work | deprecated aliases via core.errors.deprecated; tests/test_api_vocabulary.py |
| no EUR in examples and docs except the alias note | done (grep clean) |
| error messages in the user's units | PropertyError with fluid, inputs in the chart's units and the state asked for; fluid checked in constructor, from_spec and setter |
| test_api_vocabulary.py checks the public names against a frozen list | done, plus signatures with units=, IP factors, hashing, printing |

Full suite: 350 passed on CoolProp 8 (4.7 min); 111 passed each on 7.2 and 6.8.
Review: 4 blocking (fluid setter leaving a broken spec, PropertyError and UnitSystem not
picklable, EUR warning attributed to the library), all fixed in 45c2a86 with tests.
Deferred (noted in open_items.md): explicit constructors instead of object.__setattr__,
narrower catches in tracer.py.
