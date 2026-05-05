# Sparse Autoencoder Research Papers

This page collects stable starting points for SAELens work. Prefer these
primary sources over uncited blog summaries when checking concepts, training
recipes, or evaluation terminology.

## Sparse Autoencoders For Interpretability

- **Cunningham et al. (2023), "Sparse Autoencoders Find Highly Interpretable Features in Language Models"**:
  early SAE work on decomposing language-model activations into sparse,
  interpretable features. [arXiv:2309.08600](https://arxiv.org/abs/2309.08600)
- **Bricken et al. (2023), "Towards Monosemanticity: Decomposing Language Models With Dictionary Learning"**:
  Anthropic's dictionary-learning framing for feature discovery in language
  models. [Transformer Circuits](https://transformer-circuits.pub/2023/monosemantic-features/index.html)
- **Gao et al. (2024), "Scaling and evaluating sparse autoencoders"**:
  scaling and evaluation work for SAE training runs. [arXiv:2406.04093](https://arxiv.org/abs/2406.04093)
- **Templeton et al. (2024), "Scaling Monosemanticity: Extracting Interpretable Features from Claude 3 Sonnet"**:
  large-scale Anthropic feature-extraction work using sparse autoencoders.
  [Transformer Circuits](https://transformer-circuits.pub/2024/scaling-monosemanticity/index.html)

## Circuits And Background

- **Olah et al. (2020), "Zoom In: An Introduction to Circuits"**:
  background on mechanistic interpretability and circuit-style analysis.
  [Distill](https://distill.pub/2020/circuits/zoom-in/)
- **Elhage et al. (2021), "A Mathematical Framework for Transformer Circuits"**:
  transformer-circuits vocabulary and decomposition background.
  [Transformer Circuits](https://transformer-circuits.pub/2021/framework/index.html)

## Tooling

- **SAELens**: the Python library this skill targets.
  [GitHub](https://github.com/jbloomAus/SAELens)
- **Neuronpedia**: public browser for SAE features and dashboards.
  [Website](https://www.neuronpedia.org/)
