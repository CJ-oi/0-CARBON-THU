# 贡献说明

欢迎提交数据更正、来源补充、计算问题和功能改进。

## 数据更正

请说明：

- 园区标准名称和 `park_id`；
- 需要更正的字段；
- 原值与建议值；
- 官方或原始来源链接；
- 统计年度、空间边界、单位和材料日期；
- 是否允许公开展示。

## 新增来源

来源应为正常公开访问的政府、园区、行业机构、标准发布方或高质量研究机构页面。请勿提交需要绕过登录、付费墙、验证码或技术限制的入口。

## 代码修改

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
zcpark build --output site --feasibility-input data/assessments/example.json
zcpark validate --site site
node --check static/app.js
```

所有公开指标和项目参数应区分：公开事实、候选事实、指南参数、示范参数、供应商报价、可研参数和实测数据。
