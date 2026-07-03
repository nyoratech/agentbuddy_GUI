import reflex as rx

from finbuddy.components.container import container
from finbuddy.components.intro import type_writer, spline


def auth_layout(*args):
    """The shared layout for the login and sign up pages."""
    return rx.box(
        rx.center(
            rx.box(
                rx.vstack(
                    # Header section inside the central box
                    rx.hstack(
                        rx.hstack(
                            rx.heading(
                                "Finbuddy",
                                size="9",
                                color="white",
                                weight="medium",
                                font_family="EB Garamond, Garamond, serif"
                            ),
                            rx.image(
                                src="/finbuddy_logo2.png",  # or "assets/finbuddy_logo.png" depending on your static path
                                alt="FinBuddy Logo",
                                height="75px",  # Adjust as needed
                                width="auto"
                            ),
                            justify="center",
                            gap="0.4em",
                            align="center",
                            width="100%",
                            ),
                        # rx.spacer(),
                        # rx.hstack(
                        #     rx.text("News", cursor="pointer", _hover={"color": "white"}),
                        #     rx.text("About Us", cursor="pointer", _hover={"color": "white"}),
                        #     spacing="4",
                        # ),
                        align="center",
                        width="100%",
                        padding_bottom="2vh",
                        background="transparent"  # Added white background to header
                    ),

                    # Main content area
                    rx.vstack(
                        *args,
                        spacing="4",
                        align_items="center",
                        justify="center",
                        width="100%",
                        background="transparent",  # Ensure content area is white too
                        overflow="visible",
                    ),
                    spacing="3",
                    align_items="center",
                    padding="2rem",
                    background="transparent"  # This is the key change - using 'background' instead of 'background_color'
                ),
                width="900px",
                min_height="500px",
                height="auto",
                background="rgba(0, 51, 102, 0.3)",  # Dark blue, 90% transparent
                border_radius="15px",
                box_shadow="0 8px 32px 0 rgba(31, 38, 135, 0.37)",
                backdrop_filter="blur(10px)",
                style={
                    "border": "1px solid rgba(255, 255, 255, 0.18)",
                    "-webkit-backdrop-filter": "blur(10px)",
                }
            ),
            width="100%",
            height="100%"
        ),
        background="linear-gradient(135deg, #041a30, #00080f 50%, #041a30)",
        width="100vw",
        height="100vh"
    )


    # rx.vstack(rx.heading(
    #                    type_writer(
    #                        sequence=[
    #                            """Generate portfolio for slowing economic environment,
    #                             sticky inflation,
    #                             and avoid environmental impact """,
    #                                          300,
    #                            """Generate long only portfolio with top 2 sectors,
    #                            ranked by median of P/E ratio""",
    #                                         1000  ,
    #                            """
    #                            I need a 60/40 portfolio on USA
    #                            include a ladder of USA bonds for fixed income
    #                            exclude 20% companies not enviromentally friendly
    #                            """ ,
    #                            500,
    #                            """
    #                           I wanto to build a portfolio focused on tech and top 3 related sectors
    #                           I want to reduce social impact
    #                           """,
    #                            700,
    #                            """I want a portfolio that can profit during USA election and lowering rates scenario
    #                            keep environmental impact to minimum"""
    #                            ,
    #                             1000,
    #                            """I want to generate a 130/30 diversified basket on AI
    #                               tech stock should weight max 50% """
    #                            ,
    #                            1200
    #                        ],
    #                     #style={'fontSize': '12em', 'type':'Chopin'}
    #                     wrapper="span"
    #                 #"Generate long only portfolio with top 2 sectors ranked by median of P/E ratio"],
    #                 #loop='Loop.Infinite'
    #                 ),
    #                  color_scheme="cyan",
    #                  #high_contrast=True
    #                ),
    #
    #
    #     align_items="center",
    #     justify="center",
    #     background=rx.color("white", 1),
    #     # border="1px solid #eaeaea",
    #     padding="16px",
    #     width="400px",
    #     height="200px",
    #     border_radius="8px",
    #     ),
