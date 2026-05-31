"""Report rendering service."""

import json
from datetime import UTC, datetime

from tiko.domain.reporting import RenderedReport, ReportArtifact, ReportFormat


class ReportRenderService:
    """Render structured report artifacts into human-readable documents."""

    def render(
        self,
        report: ReportArtifact,
        report_format: ReportFormat = "markdown",
    ) -> RenderedReport:
        """Render a report artifact.

        Args:
            report: Structured report artifact.
            report_format: Requested render format.

        Returns:
            Rendered report document.

        Raises:
            ValueError: If the requested format is unsupported.
        """

        if report_format != "markdown":
            raise ValueError("Only markdown report rendering is supported.")
        return self._render_markdown(report)

    def _render_markdown(self, report: ReportArtifact) -> RenderedReport:
        """Render a report artifact as Markdown.

        Args:
            report: Structured report artifact.

        Returns:
            Markdown rendered report.
        """

        lines = [
            f"# {report.title}",
            "",
            "- Report ID: " + str(report.report_id),
            "- Report Type: " + report.report_type,
            "- Run ID: " + str(report.run_id),
            "- Created At: " + report.created_at.isoformat(),
            "- Created At Sim Time: " + report.created_at_sim_time.isoformat(),
            "",
            "## Summary",
            "",
            report.summary,
        ]
        if report.sections:
            lines.extend(["", "## Sections", ""])
            for section_name, section_value in report.sections.items():
                lines.extend(
                    [
                        f"### {self._format_section_title(section_name)}",
                        "",
                        self._render_section_value(section_value),
                        "",
                    ]
                )
        content = "\n".join(lines).rstrip() + "\n"
        return RenderedReport(
            report_id=report.report_id,
            report_type=report.report_type,
            format="markdown",
            title=report.title,
            content=content,
            rendered_at=datetime.now(UTC),
        )

    def _format_section_title(self, section_name: str) -> str:
        """Format a section key as a Markdown heading.

        Args:
            section_name: Structured section key.

        Returns:
            Human-readable section title.
        """

        return section_name.replace("_", " ").title()

    def _render_section_value(self, section_value: object) -> str:
        """Render one structured section value.

        Args:
            section_value: Section payload value.

        Returns:
            Markdown section body.
        """

        if isinstance(section_value, dict | list):
            serialized_value = json.dumps(
                section_value,
                default=str,
                indent=2,
                sort_keys=True,
            )
            return "```json\n" + serialized_value + "\n```"
        if section_value is None:
            return "`null`"
        return str(section_value)
