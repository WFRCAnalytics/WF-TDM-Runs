# _dev

Supporting development artifacts — presentations, proposals, and working
documents. Not part of the model run framework itself.

## Contents

- `tdm-run-management-framework-proposal.qmd` — Quarto RevealJS presentation
  proposing the framework to the WFRC/MAG analytics group, targeting pilot
  approval. 15 slides, WFRC brand colors.
- `styles.css` — WFRC brand color stylesheet for the presentation. Must sit
  in the same folder as the `.qmd` file to be picked up at render time.

## Rendering the presentation

```bash
quarto preview _dev/tdm-run-management-framework-proposal.qmd
# or
quarto render _dev/tdm-run-management-framework-proposal.qmd
```
