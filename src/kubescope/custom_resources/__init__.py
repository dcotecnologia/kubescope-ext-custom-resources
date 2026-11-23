"""Custom Resources for KubeScope: the custom resource definitions of the
cluster in the side menu, a list for each kind and, for the ExternalSecrets,
how their sync went and a resync."""

from kubescope.sdk import Context


def activate(ctx: Context) -> None:
    """What the app calls to run the extension."""
    from kubescope.custom_resources import extension

    extension.activate(ctx)
