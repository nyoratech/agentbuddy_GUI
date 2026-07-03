import reflex as rx

from finbuddy.components import loading_icon
from finbuddy.state import QA, State
from finbuddy.components.prompts import *

from typing import Optional, List, Dict, Tuple, Any, Union
from YourIndexingAI.rx_interface import load_images_from_directory
import plotly.express as px
from plotly.graph_objects import Figure as Figure_plotly
import pandas as pd
message_style = dict(display="inline-block",
                     padding="1em",
                     border_radius="8px",
                     max_width=["200em"]#, "30em", "50em", "50em", "50em", "50em"]
                     )


def message(qa: rx.Var[QA]) -> rx.Component:
    """A single question/answer message.

    Args:
        qa: The question/answer pair.

    Returns:
        A component displaying the question/answer pair.
    """
    
    return rx.box(
        rx.box(
            rx.markdown(
                qa.to(QA).question,
                background_color=rx.color("mauve", 2),
                color=rx.color("mauve", 12),
                text_align="left",
                box_shadow="0 6px 24px rgba(0, 0, 0, 0.15)",
                **message_style,
            ),
            text_align="left",
            margin_top="1em",
        ),
        rx.box(
            rx.cond(
                qa.to(QA).answer.contains("Generating"),
                rx.progress(value=State.job_update_progress, max=100, color_scheme="blue", width="30%"),
                None
            ),
            rx.markdown(
                qa.to(QA).answer,
                background_color=rx.color("white", 1),
                color=rx.color("accent", 12),
                text_align="left",
                **message_style,

            ),
            text_align="left",
            padding_top="1em",
            max_width="200em"
        ),
        width="100%",    )



def plotly_single_plot(plot_fig: rx.Var[Tuple[Figure_plotly, Dict[str, str]]]) -> rx.Component:
    # cannot do anything with var here
    return rx.plotly(data=plot_fig.to(Tuple[Figure_plotly, Dict[str, str]])[0].to(Figure_plotly),
                     layout=plot_fig.to(Tuple[Figure_plotly, Dict[str, str]])[1],
                     height="400px"
                     )

def single_table(table_data: rx.Var[Tuple[pd.DataFrame, Dict[str, str]]]) -> rx.Component:
    # cannot do anything with var here
    return rx.data_table(
        data=table_data.to(Tuple[pd.DataFrame, Dict[str, str]])[0],
        pagination=True,
        search=True,
        sort=True,
        height="400px"
    )



def js_single_plot(plot_data: rx.Var[Tuple[str, Dict[str, str]]]) -> rx.Component:
    """A single Lightweight Chart plot that is self-contained."""
    config = plot_data.to(Tuple[str, Dict[str, str]])[1]
    # xaxis_label = config.get("xaxis", "X-Axis") # Not directly used for ID generation or current heading
    # original_title = config.get("title", "Chart") # Not used for ID generation or current heading
    plot_name = config.get("plot_name", "Chart") # Used for rx.heading and as base for JS IDs

    # ID for the Reflex component (rx.box id) and passed to JS for chart.createChart()
    chart_id = f"chart_{plot_name}" # This is used for rx.box(id=...) and passed to JS

    # container_id and band_id are now generated within JavaScript using 'plot_name'
    # The line 'title = title + ":" + plot_name' is removed as the concatenated 'title' is not used.
    log_line_create_chart = 'console.log(`LW Chart: About to create chart. Element ID: ${el.id}, Width: ${el.clientWidth}, Height: ${el.offsetHeight}`);'
    log_line_interaction_debug = 'console.log(`LW Chart Interaction Debug: clickY=${clickYRelativeToContainer.toFixed(2)}, containerH=${rect.height.toFixed(2)}, xThreshold=${xAxisThresholdPx}, comparisonY=${(rect.height - xAxisThresholdPx).toFixed(2)}`);'
    init_js = f"""
(function() {{
    // Python passes 'plot_name' (e.g., "portfolio_factors_1")
    // and 'chart_id' (e.g., "chart_portfolio_factors_1")
    const basePlotNameFromPy = '{plot_name}';
    const chartElementIdFromPy = 'chart_'+'{plot_name}';

    // Use the chart_id passed from Python for the chart element
    const chartElementId = chartElementIdFromPy;

    // Construct container and band IDs in JavaScript using the base plot_name
    const chartContainerId = 'container_' + basePlotNameFromPy;
    const selectionBandId = 'band_' + basePlotNameFromPy;

    console.log('LW Chart Script starting for: ' + basePlotNameFromPy);
    console.log('LW Chart IDs: element=' + chartElementId + ', container=' + chartContainerId + ', band=' + selectionBandId);
    // Data is directly inlined from the Python f-string evaluation.
    // The Python expression plot_data.to(Tuple[str, Dict[str, str]])[0] is evaluated by Python,
    // and its string result (the JSON) is embedded directly into the JavaScript code here.
    const jsonData = {plot_data.to(Tuple[str, Dict[str, str]])[0]};
    console.log('LW Chart: Attempting to use inlined real data. Value:', jsonData);

    // Validate that jsonData is an array, as Lightweight Charts expects series data to be an array.
    if (!Array.isArray(jsonData)) {{
        console.error('LW Chart: Inlined jsonData is NOT an array! This will likely cause chart errors. Check Python expression and state variable. Value received:', jsonData);
        // Fallback to an empty array to prevent seriesInstance.setData from failing if it expects an array.
        jsonData = []; 
    }} else if (jsonData.length === 0) {{
        console.warn('LW Chart: Inlined jsonData is an empty array. The chart will be empty but should not error.');
    }} else {{
        console.log('LW Chart: Successfully inlined jsonData. Length:', jsonData.length, 'First item example:', jsonData[0]);
    }}

    let chartInstance = null;
    let seriesInstance = null;

    function initializeChart() {{
        console.log('LW Chart: initializeChart() called.');
        if (chartInstance) {{
            console.log('LW Chart: Already initialized.');
            return true;
        }}

        if (typeof LightweightCharts === 'undefined') {{
            console.log('LW Chart: LightweightCharts library not found, retrying...');
            setTimeout(() => initializeChart(), 100);
            return false;
        }}

        const el = document.getElementById(chartElementId);
        if (!el) {{
            console.log(`LW Chart: Element with ID '{{chartElementId}}' not found, retrying...`);
            setTimeout(() => initializeChart(), 100);
            return false;
        }}
        
        {log_line_create_chart}
        console.log('LW Chart: Creating chart instance.');
        chartInstance = LightweightCharts.createChart(el, {{
            width: el.clientWidth,
            height: 650,
            autoSize: true,
            layout: {{ background: {{ color: 'transparent' }}, textColor: '#333' }},
            grid:   {{ vertLines: {{ color: '#f0f0f0' }}, horzLines: {{ color: '#f0f0f0' }} }},
        }});
        seriesInstance = chartInstance.addLineSeries({{ color: '#4a90e2', lineWidth: 2 }});
        console.log('LW Chart: Chart and series instances created.');

        if (window.ResizeObserver) {{
            new ResizeObserver(entries => {{
                if (!entries || !entries.length || !chartInstance) return;
                const entry = entries[0];
                if (entry.contentRect && entry.contentRect.width > 0) {{
                    chartInstance.applyOptions({{ width: entry.contentRect.width }});
                }}
            }}).observe(el);
        }}

        const chartContainerForZoom = document.getElementById(chartContainerId);
        const selectionBand = document.getElementById(selectionBandId);
        let isDragging = false;
        let dragStartLogical = null;

        if (chartContainerForZoom && selectionBand) {{
            chartContainerForZoom.addEventListener('mousedown', (event) => {{
                if (event.button !== 0 || !chartInstance) return;

                const rect = chartContainerForZoom.getBoundingClientRect();
                const clickYRelativeToContainer = event.clientY - rect.top;
                const xAxisThresholdPx = 45; // Approximate height of the X-axis area -- Increased from 30

                // New detailed debug log
                {log_line_interaction_debug}

                // Check if the click is within the bottom area (likely the X-axis/time-scale)
                if (clickYRelativeToContainer > (rect.height - xAxisThresholdPx)) {{
                    console.log('LW Chart: Mousedown on X-axis area, enabling native chart pan.');
                    chartInstance.applyOptions({{ 
                        handleScroll: {{ pressedMouseMove: true }}, // Allow native drag-panning
                        handleScale: {{ mouseWheel: true }} // Keep mouse wheel zoom enabled generally
                    }});
                    // Do NOT set isDragging = true or show selectionBand. Let the chart handle it.
                    return; 
                }}

                // If click is not on X-axis, proceed with custom drag-to-zoom for the main plot area.
                console.log('LW Chart: Mousedown on main plot area, initiating custom zoom.');
                dragStartLogical = chartInstance.timeScale().coordinateToLogical(event.clientX - rect.left);
                if (dragStartLogical === null) return; // Click was outside of plot area time-wise

                isDragging = true;
                selectionBand.style.left = (event.clientX - rect.left) + 'px';
                selectionBand.style.top = '0px'; // Align band to the top of the container
                selectionBand.style.width = '0px';
                selectionBand.style.height = rect.height + 'px'; // Band covers full container height
                selectionBand.style.display = 'block';
                
                // Disable chart's own drag-scrolling and mouse-wheel scaling during our custom zoom
                chartInstance.applyOptions({{
                    handleScroll: {{ pressedMouseMove: false }}, // Disable native drag-panning
                    handleScale: {{ mouseWheel: false }} // Disable mouse wheel zoom during drag-zoom
                }});
            }});
            document.addEventListener('mousemove', (event) => {{
                if (!isDragging || !chartInstance) return;
                const rect = chartContainerForZoom.getBoundingClientRect();
                const currentX = event.clientX - rect.left;
                const initialX = parseFloat(selectionBand.style.left);
                const width = Math.abs(currentX - initialX);
                const newLeft = Math.min(currentX, initialX);
                selectionBand.style.left = newLeft + 'px';
                selectionBand.style.width = width + 'px';
            }});
            document.addEventListener('mouseup', (event) => {{
                if (!isDragging || !chartInstance) return;
                isDragging = false;
                selectionBand.style.display = 'none';
                const rect = chartContainerForZoom.getBoundingClientRect();
                const x = event.clientX - rect.left;
                const dragEndLogical = chartInstance.timeScale().coordinateToLogical(x);
                if (dragStartLogical !== null && dragEndLogical !== null) {{
                    const from = Math.min(dragStartLogical, dragEndLogical);
                    const to = Math.max(dragStartLogical, dragEndLogical);
                    if (from !== to) chartInstance.timeScale().setVisibleLogicalRange({{ from, to }});
                }}
                chartInstance.applyOptions({{ handleScroll: {{ pressedMouseMove: true }}, handleScale: {{ mouseWheel: true }} }});
            }});
            chartContainerForZoom.addEventListener('dblclick', () => {{
                if (chartInstance) chartInstance.timeScale().fitContent();
            }});
        }}
        console.log('LW Chart: Initialization complete.');
        return true;
    }}

    function renderData(data) {{
        console.log('LW Chart: renderData() called.');
        if (!initializeChart()) {{
            console.log('LW Chart: Waiting for initialization to render data.');
            setTimeout(() => renderData(data), 150);
            return;
        }}
        if (data && seriesInstance) {{
            console.log('LW Chart: Setting data on series instance.');
            seriesInstance.setData(data);
            if (data.length > 0) {{
                 chartInstance.timeScale().fitContent();
                 console.log('LW Chart: Applied fitContent.');
            }}
        }} else {{
            console.log('LW Chart: renderData - data or seriesInstance is missing.', {{'hasData': !!data, 'hasSeries': !!seriesInstance}});
        }}
    }}
    
    console.log('LW Chart: Calling renderData for the first time.');
    renderData(jsonData);
}})();
"""

    return rx.box(
        rx.heading(plot_name, size="4", margin_bottom="0.5em", text_align="center"),
        rx.hstack(
            rx.text(
                config.get("yaxis", "Y-Axis"),
                style={
                    "writing_mode": "vertical-rl",
                    "transform": "rotate(180deg)",
                    "white_space": "nowrap",
                },
                size="2",
                color_scheme="gray",
                margin_right="0.5em",
                align_self="center",
            ),
            # This is the main chart area box
            rx.box(
                rx.box(id=chart_id, width="100%", height="100%"), # Chart drawing div
                rx.box(
                    # This ID must match the 'selectionBandId' constructed in JavaScript
                    id=f"band_{plot_name}",
                    position="absolute", display="none",
                    bg="rgba(0, 123, 255, 0.2)", border="1px solid rgba(0, 123, 255, 0.5)",
                    z_index="10", top="0", left="0", width="0px", height="100%"
                ),
                # This ID must match the 'chartContainerId' constructed in JavaScript
                id=f"container_{plot_name}",
                position="relative", width="100%", height="300px",
                flex_grow="1"
            ),
            spacing="1",
            align_items="center",
            width="100%",
            height="300px", # Match height of the chart area for alignment
            margin_bottom="0.5em" # Retain original margin
        ),
        rx.text(config.get("xaxis", "X-Axis"), size="2", color_scheme="gray", text_align="center"),
        rx.script(src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js", strategy="afterInteractive"),
        rx.script(init_js),
        border="1px solid #eee", padding="1em", border_radius="8px", width="100%", box_shadow="0 6px 24px rgba(0, 0, 0, 0.15)", margin_top="1.5em",
    )

def message_content(qa: QA) -> rx.Component:
    """Render a message."""
    return message(qa)

def table_content(data: Tuple[pd.DataFrame, Dict[str, str]]) -> rx.Component:
    """Render a table."""
    return single_table(data)

def plot_content(data: Tuple[Figure_plotly, Dict[str, str]]) -> rx.Component:
    """Render a plot."""
    return plotly_single_plot(data)

# Function to handle individual content items based on type
def render_content_item(item):
    """Render a single content item based on its type.

    Args:
        item: A tuple of (content_type, content, timestamp)

    Returns:
        The appropriate component for the content type
    """
    content_type = item[0]
    content = item[1]

    return rx.match(
        content_type,
        ("message", message(content)),
        ("table", single_table(content)),
        ("plot", js_single_plot(content)),
        rx.text("Unknown format")
    )

def chat() -> rx.Component:
    """List all the content in a single conversation in chronological order."""
    
    # First, create a properly typed data variable
    # Use a simpler approach with just the .get() method and direct type conversion
    #data = State.combined_content.get(State.current_chat, []).to(List[Tuple[str, Any, float]])
    
    return rx.vstack(
        rx.foreach(
            State.current_chat_content.to(List[Tuple[str, Union[QA, Tuple[str, Dict[str, str]], Tuple[str, Dict[str, str]], Tuple[pd.DataFrame, Dict[str, str]]], float]]),
            render_content_item
        ),
        max_width="60em",
        width="100%",
        margin_left="20%",
        padding_y="2em",
    )

def action_bar() -> rx.Component:
    """The action bar to send a new message - fixed at bottom with 70% width."""
    return rx.box(
        rx.center(
            rx.vstack(
                rx.form(
                    rx.hstack(
                        rx.text_area(
                            placeholder="Type something...",
                            value=State.question,
                            on_change=State.set_question,
                            flex=1,
                            rows="10",
                            flexGrow=1,
                            width="100%",
                            whiteSpace='pre-wrap',
                            id="question",
                            align_self="flex-end",  # Align text area bottom with buttons
                            background_color=rx.color("mauve", 2)
                        ),
                        rx.vstack(
                            rx.button(
                                rx.hstack(
                                    rx.box(
                                        rx.icon(tag="refresh-ccw", color=rx.color("mauve", 10)),
                                        background_color=rx.color("sky", 3),
                                        border_radius="50%",
                                        padding="0.5em",
                                    ),
                                    rx.box(width="1em", height="1em"),  # Spacer to match Button 2
                                    spacing="1",
                                    align_items="center",
                                ),
                                on_click=State.set_plots_frontend,
                                width="5em",
                                height="3em",
                                background_color="transparent",
                                padding_x="0",
                            ),
                            rx.button(
                                rx.hstack(
                                    rx.box(  # Main icon
                                        rx.icon(tag="circle-arrow-up", color=rx.color("mauve", 10)),
                                        background_color=rx.color("sky", 3),
                                        border_radius="50%",
                                        padding="0.5em",
                                    ),
                                    rx.box(  # Loading icon container (always present)
                                        rx.cond(
                                            State.processing,
                                            loading_icon(height="1em"),
                                            rx.box(width="1em", height="1em"),  # Invisible spacer when not loading
                                        ),
                                        width="1em",  # Match loading icon width
                                        height="1em",
                                    ),
                                    spacing="1",
                                    align_items="center",
                                ),
                                type="submit",
                                width="5em",
                                height="3em",
                                background_color="transparent",
                                padding_x="0",
                            ),
                            spacing="1",
                            align_items="center",  # Changed to center alignment
                            justify="center",  # Changed to center justification
                            height="100%",
                        ),
                        align_items="flex-end",  # Align both text area and buttons to bottom
                        width="100%",
                        spacing="0",

                    ),
                    is_disabled=State.processing,
                    padding="10",
                    on_submit=State.process_question_event,
                    reset_on_submit=True,
                    width="100%",
                ),
                rx.hstack(
                        rx.menu.root(
                        rx.menu.trigger(
                            rx.button(
                                "Equity",
                                variant="soft",
                                font_size="12px",
                                color=rx.color("mauve", 9),
                                background_color=rx.color("mauve", 2),
                            )
                        ),

                        rx.menu.content(
                            rx.menu.item(
                                "SP500-ESG",
                                on_select=rx.set_value("question", eq_portfolio_example1),

                            ),
                            rx.menu.item(
                                    "Tech-ESG",
                                on_click=rx.set_value("question", eq_portfolio_example2),
                            ),
                            rx.menu.item(
                                    "Tilt to quality",
                                on_click=rx.set_value("question", eq_portfolio_example3),
                            ),
                            rx.menu.item(
                                    "Index Tracking",
                                on_click=rx.set_value("question", eq_portfolio_example4),
                            ),
                            variant="soft",
                            border_color=rx.color("mauve", 2),
                            color=rx.color("mauve", 9),
                            background_color=rx.color("mauve", 2),
                        )),
                        rx.menu.root(
                        rx.menu.trigger(
                            rx.button(
                                "Fixed Income",
                                variant="soft",
                                font_size="12px",
                                color=rx.color("mauve", 9),
                                background_color=rx.color("mauve", 2),
                            )
                        ),

                        rx.menu.content(
                            rx.menu.item(
                                    "Gov Bond Ladder",
                                on_click=rx.set_value("question", fi_portfolio_example1),
                            ),
                            rx.menu.item(
                                    "Gov Bond rolling",
                                on_click=rx.set_value("question", fi_portfolio_example2),
                            ),
                            variant="soft",
                            border_color=rx.color("mauve", 2),
                            color=rx.color("mauve", 9),
                            background_color=rx.color("mauve", 2),
                        )),
                        rx.menu.root(
                        rx.menu.trigger(
                            rx.button(
                                "Asset allocation",
                                variant="soft",
                                font_size="12px",
                                color=rx.color("mauve", 9),
                                background_color=rx.color("mauve", 2),
                            )
                        ),

                        rx.menu.content(
                            rx.menu.item(
                                "60/40 portfolio",
                                on_select=rx.set_value("question", asset_allocation_example1),

                            ),
                            rx.menu.item(
                                    "50/50 portfolio",
                                on_click=rx.set_value("question", asset_allocation_example2),
                            ),
                            variant="soft",
                            border_color=rx.color("mauve", 2),
                            color=rx.color("mauve", 9),
                            background_color=rx.color("mauve", 2),
                        )),
                        rx.menu.root(
                        rx.menu.trigger(
                            rx.button(
                                "Active ETFs",
                                variant="soft",
                                font_size="12px",
                                color=rx.color("mauve", 9),
                                background_color=rx.color("mauve", 2),
                            )
                        ),

                        rx.menu.content(
                            rx.menu.item(
                                "ETF emerging markets",
                                on_select=rx.set_value("question", etf_example1),

                            ),
                            rx.menu.item(
                                    "quality/growth",
                                on_click=rx.set_value("question", etf_example2),
                            ),
                        variant="soft",
                            border_color=rx.color("mauve", 2),
                            color=rx.color("mauve", 9),
                            background_color=rx.color("mauve", 2),
                        )),
                        rx.menu.root(
                        rx.menu.trigger(
                            rx.button(
                                "...",
                                variant="soft",
                                font_size="12px",
                                color=rx.color("mauve", 9),
                                background_color=rx.color("mauve", 2),
                            )
                        )),
                justify="start",
                width="100%",
                ),
                        
                rx.text(
                    "Imagine, Type, Trade",
                    text_align="center",
                    font_size=".75em",
                    color=rx.color("mauve", 10),
                ),
                align_items="center",
                width="60%",
                background_color=rx.color("white", 1),
                border_top=f"1px solid {rx.color('mauve', 3)}",
                padding_y="16px",
                backdrop_filter="auto",
            ),
            position="fixed",
            bottom="0",
            left="0",
            right="0",
            width="100%",
            z_index="1000",
            background_color="#FFFFFF",
        )
    )


def chat_action_bar() -> rx.Component:
    return rx.vstack(
        chat_container()

    )
def chat_container() -> rx.Component:
    """Container that holds both chat and action bar with proper scrolling."""
    return rx.grid(
        rx.box(
            chat(),
            overflow_y="auto",
            width="100%",
            height="100%",
            padding_bottom="20em",
        ),
        rx.box(
            action_bar(),
            width="100%",
        ),
        grid_template_rows="1fr auto",
        height="100%",
        width="100%",
        spacing="0",
    )