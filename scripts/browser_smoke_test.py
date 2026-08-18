from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from capture_and_render import embedded_site_html, launch_browser


def main() -> int:
    parser = argparse.ArgumentParser(description="Run browser-level smoke tests for the built site")
    parser.add_argument("--site", default="site", help="built site directory")
    parser.add_argument("--output", default="outputs/browser_smoke_test.json", help="JSON result path")
    args = parser.parse_args()

    site = Path(args.site).resolve()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not (site / "index.html").exists():
        raise SystemExit(f"Missing site: {site / 'index.html'}")

    checks: list[dict[str, object]] = []

    def record(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        print(f"{'PASS' if passed else 'FAIL'}: {name} {detail}", flush=True)

    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1050},
            device_scale_factor=1,
            accept_downloads=True,
        )
        page = context.new_page()
        page.set_default_timeout(5000)
        console_errors: list[str] = []
        page_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.set_content(embedded_site_html(site), wait_until="load", timeout=120_000)
        page.wait_for_function("document.documentElement.dataset.selftest === 'pass'", timeout=60_000)
        page.wait_for_selector("#kpiGrid .kpi")

        record("内置自检", page.get_attribute("html", "data-selftest") == "pass")
        record("无禁用按钮", page.locator("button:disabled").count() == 0)
        record("无空锚点", page.locator('a[href="#"], a[href="javascript:void(0)"], a:not([href])').count() == 0)
        record("五项工作入口", page.locator(".five-tab").count() == 5)
        record("报告链接", page.locator("#reportLinks a").count() >= 6, str(page.locator("#reportLinks a").count()))

        # Map filters, coordinate positioning and park detail.
        for map_filter in ("全国", "国家级", "广东", "全球"):
            button = page.locator(f'.map-filter[data-map-filter="{map_filter}"]')
            button.click()
            page.wait_for_timeout(150)
            active = button.get_attribute("class") or ""
            count_text = page.locator("#mapCount").inner_text()
            record(f"地图筛选：{map_filter}", "active" in active and any(ch.isdigit() for ch in count_text), count_text)

        page.locator('.map-filter[data-map-filter="全国"]').click()
        page.locator("#mapSearch").fill("北京经济技术开发区")
        page.wait_for_timeout(200)
        marker_count = page.locator(".map-marker-group").count()
        record("园区名称定位", marker_count == 1, f"marker_count={marker_count}")
        if marker_count:
            marker = page.locator(".map-marker-group").first
            marker.focus()
            marker.press("Enter")
            page.wait_for_timeout(150)
            detail_text = page.locator("#parkDetail").inner_text()
            record("地图点位联动资料卡", "北京经济技术开发区" in detail_text and "经度" in detail_text and "纬度" in detail_text)
        page.locator("#mapReset").click()
        record("地图复位", page.locator("#mapSearch").input_value() == "")

        # Dynamic feed filters.
        topic_buttons = page.locator(".topic-filter")
        record("动态分类入口", topic_buttons.count() >= 4, str(topic_buttons.count()))
        if topic_buttons.count() > 1:
            topic_buttons.nth(1).click()
            page.wait_for_timeout(100)
            record("动态分类切换", "active" in (topic_buttons.nth(1).get_attribute("class") or ""))
        page.locator('.topic-filter[data-topic="全部"]').click()
        if page.locator("#showMoreUpdates").is_visible():
            before = page.locator("#updatesGrid .update-card").count()
            page.locator("#showMoreUpdates").click()
            after = page.locator("#updatesGrid .update-card").count()
            record("动态分批展开", after >= before, f"{before}->{after}")
        else:
            record("动态分批展开", True, "当前记录已全部显示")

        # Five tabs and data-task workflow.
        for panel in ("data-ready", "current-state", "gap", "reduce", "cost"):
            page.locator(f'.five-tab[data-panel="{panel}"]').click()
            record(f"五项工作切换：{panel}", "active" in (page.locator(f"#{panel}").get_attribute("class") or ""))

        page.locator('.five-tab[data-panel="data-ready"]').click()
        page.locator("#checkAllP0").click()
        readiness = page.locator("#readinessScore").inner_text()
        record("P0字段批量勾选", readiness.endswith("%") and readiness != "0%", readiness)
        page.locator("#clearChecklist").click()
        page.locator("#generateTasks").click()
        task_count = page.locator("#taskList .task-item").count()
        record("生成补数任务", task_count > 0, str(task_count))

        # Current-state profile.
        page.locator('.five-tab[data-panel="current-state"]').click()
        option_count = page.locator("#stateParkSelect option").count()
        if option_count > 1:
            value = page.locator("#stateParkSelect option").nth(1).get_attribute("value")
            if value:
                page.locator("#stateParkSelect").select_option(value)
                profile_text = page.locator("#currentProfile").inner_text()
                record("园区现状画像", len(profile_text) > 80 and "产业类型" in profile_text, profile_text[:100])
            else:
                record("园区现状画像", False, "首个园区选项无值")
        else:
            record("园区现状画像", False, "无园区选项")

        # Gap calculation also prepares measure options.
        page.locator('.five-tab[data-panel="gap"]').click()
        page.locator("#loadGapDemo").click()
        page.locator("#runGap").click()
        gap_text = page.locator("#gapResult").inner_text()
        advice_text = page.locator("#reductionAdvice").inner_text()
        record("指标差距核算", "单位综合能耗碳排放" in gap_text and "差距" in gap_text, gap_text[:120])
        record("差距对应措施清单", len(advice_text) > 80 and "先核实" in advice_text, advice_text[:120])

        # Measure filtering and selection.
        page.locator('.five-tab[data-panel="reduce"]').click()
        page.locator("#selectBasicMeasures").click()
        checked = page.locator('#measuresGrid input[type="checkbox"]:checked').count()
        record("基础改进措施批量选择", checked > 0, str(checked))
        page.locator("#measureSearch").fill("余热")
        page.wait_for_timeout(100)
        record("措施检索", page.locator("#measuresGrid .measure-card").count() > 0)
        page.locator("#measureSearch").fill("")

        # Feasibility analysis, sensitivity scenarios, and dynamic project buttons.
        page.locator('.five-tab[data-panel="cost"]').click()
        page.locator("#loadProjectDemo").click()
        page.locator("#feasBoundary").check()
        page.locator("#feasEnterprise").check()
        page.locator("#runFeasibility").click()
        feasibility_text = page.locator("#feasibilityResult").inner_text()
        path_text = page.locator("#pathResult").inner_text()
        record("项目组合可行性分析", "组合投资" in feasibility_text and "年度减排" in feasibility_text, feasibility_text[:140])
        record("演示参数不形成正式结论", "不构成园区可行性结论" in feasibility_text)
        record("关键参数敏感性", "保守情景" in feasibility_text and "改善情景" in feasibility_text)
        record("年度路径与利益相关方", "年度" in path_text and len(path_text) > 80, path_text[:120])
        before_projects = page.locator("#projectTableBody tr").count()
        page.locator("#addProject").click()
        after_add = page.locator("#projectTableBody tr").count()
        record("新增项目", after_add == before_projects + 1, f"{before_projects}->{after_add}")
        if page.locator(".project-delete").count():
            page.locator(".project-delete").last.click()
            after_delete = page.locator("#projectTableBody tr").count()
            record("删除项目", after_delete == before_projects, f"{after_add}->{after_delete}")

        # Search database.
        page.locator("#dbSearch").fill("北京经济技术开发区")
        page.locator("#dbRun").click()
        db_status = page.locator("#dbStatus").inner_text()
        record("公开资料库检索", "找到" in db_status and "0 条" not in db_status, db_status)
        page.locator("#dbClear").click()
        record("公开资料库清空", page.locator("#dbSearch").input_value() == "")

        pdf_links = page.locator('#reportLinks a[download][href$=".pdf"]').count()
        record("PDF报告直接下载", pdf_links >= 1, str(pdf_links))

        record("浏览器控制台无错误", not console_errors, " | ".join(console_errors[:5]))
        record("页面运行无异常", not page_errors, " | ".join(page_errors[:5]))

        context.close()
        browser.close()

    passed = sum(1 for item in checks if item["passed"])
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site": str(site),
        "passed": passed,
        "total": len(checks),
        "ok": passed == len(checks),
        "checks": checks,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "passed": passed, "total": len(checks), "output": str(output)}, ensure_ascii=False))
    if not result["ok"]:
        for item in checks:
            if not item["passed"]:
                print(f"FAIL: {item['name']}: {item['detail']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
