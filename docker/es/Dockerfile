# 在官方 Elasticsearch 镜像基础上安装 IK 中文分词插件（analysis-ik）。
# 官方镜像不自带 IK，因此需要自建镜像。插件版本必须与 ES 版本严格一致。
FROM docker.elastic.co/elasticsearch/elasticsearch:8.17.10

RUN bin/elasticsearch-plugin install --batch \
    https://get.infini.cloud/elasticsearch/analysis-ik/8.17.10
