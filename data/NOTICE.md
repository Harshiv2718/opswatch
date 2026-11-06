# BGL source and dataset terms

The full BGL archive is obtained from the official Loghub release:

- Repository: https://github.com/logpai/loghub
- Dataset documentation: https://github.com/logpai/loghub/tree/master/BGL
- Zenodo release: https://zenodo.org/records/8196385
- Archive: https://zenodo.org/records/8196385/files/BGL.zip?download=1
- Published MD5: `4452953c470f2d95fcb32d5f6e733f7a`

Loghub license notice, as stated by the dataset publisher:

> The datasets are freely available for research or academic work, subject to the following condition: For any usage or distribution of the loghub datasets, please refer to the loghub repository URL (https://github.com/logpai/loghub) and cite the loghub paper (Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics) where applicable.
>
> The above license notice shall be included in all copies of the datasets.

The raw corpus is not included in this repository and should remain ignored by Git. Derived evaluation artifacts include short source message excerpts for research demonstration and retain this source notice. Do not assume the dataset is covered by the project's software license or a blanket commercial-use permission.

References requested by the BGL documentation:

- Adam J. Oliner and Jon Stearley. *What Supercomputers Say: A Study of Five System Logs*. IEEE/IFIP International Conference on Dependable Systems and Networks, 2007.
- Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu and Michael R. Lyu. *Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics*. IEEE International Symposium on Software Reliability Engineering, 2023.

The first raw token is an alert category: `-` denotes non-alert; other tags denote alert. These are historical alert labels, not independently verified future outage or incident outcomes.
