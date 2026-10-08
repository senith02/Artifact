"""The P4 carbon-deferral advisor (DL-033 revision 3).

A thin layer over the frozen research core. For one CI run it answers RUN NOW
or DEFER RECOMMENDED, and why. Every decision is
``scheduler_core.policy.decide()`` under the frozen ``policy_spec.yaml``; ``d̂``
comes from the frozen estimator's own ``causal_project_history`` +
``predict_4b``. Nothing here may decide on its own: the advisor only validates,
vetoes towards RUN NOW, labels, and audits (context/p4_interface.md).
"""

ADVISOR_VERSION = "0.1.0"
