import { ExportOutlined, ReadOutlined } from "@ant-design/icons";
import { Button, Modal, Spin, Typography } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { isNative, openExternalUrl } from "../lib/native";
import { wikiUrl } from "../lib/wikiLink";
import { hasWikiSummaries, loadWikiSummary, type WikiSummary } from "../lib/wikiSummary";

interface WikiLinkProps {
  itemId: number;
  name: string;
  language: string;
  label: string;
}

/**
 * Opens the item's wiki article. For languages with bundled summaries the intro is shown
 * in a modal, with a link to the full article; otherwise the wiki page opens in a browser.
 */
export default function WikiLink({ itemId, name, language, label }: WikiLinkProps) {
  const { t } = useTranslation();
  const url = wikiUrl(name, language);
  const local = hasWikiSummaries(language);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [summary, setSummary] = useState<WikiSummary | null>(null);

  const openFullArticle = () => {
    if (isNative()) {
      void openExternalUrl(url);
    } else {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  };

  const showSummary = async () => {
    setOpen(true);
    if (loaded) return;
    setLoading(true);
    setSummary(await loadWikiSummary(language, itemId));
    setLoading(false);
    setLoaded(true);
  };

  if (!local) {
    return (
      <Typography.Link
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        onClick={isNative() ? event => { event.preventDefault(); void openExternalUrl(url); } : undefined}
        title={label}
        aria-label={label}
        style={{ marginLeft: 6 }}
      >
        <ExportOutlined />
      </Typography.Link>
    );
  }

  return (
    <>
      <Button
        type="link"
        size="small"
        aria-label={label}
        title={label}
        onClick={event => { event.preventDefault(); void showSummary(); }}
        style={{ marginLeft: 4, padding: 0, height: "auto" }}
      >
        <ReadOutlined />
      </Button>
      <Modal
        open={open}
        onCancel={() => setOpen(false)}
        title={summary?.title ?? name}
        width={560}
        footer={<Button onClick={openFullArticle}>{t("wiki_summary_open")}</Button>}
      >
        {loading ? (
          <div style={{ textAlign: "center", padding: 24 }}><Spin /></div>
        ) : summary ? (
          <>
            <Typography.Paragraph style={{ whiteSpace: "pre-wrap" }}>{summary.extract}</Typography.Paragraph>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t("wiki_summary_source")}
            </Typography.Text>
          </>
        ) : (
          <Typography.Paragraph type="secondary">{t("wiki_summary_missing")}</Typography.Paragraph>
        )}
      </Modal>
    </>
  );
}
