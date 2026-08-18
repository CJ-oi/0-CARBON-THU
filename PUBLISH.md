# 公开发布与更新说明

当前公开仓库：`https://github.com/CJ-oi/0-CARBON-THU/`  
当前公开网站：`https://cj-oi.github.io/0-CARBON-THU/`


## 六、本地验证

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
zcpark build --output site --feasibility-input data/assessments/example.json
python scripts/capture_and_render.py --site site
zcpark validate --site site
node --check static/app.js
```
