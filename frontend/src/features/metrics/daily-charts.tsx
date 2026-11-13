import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts'
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Typography } from '@/components/typography'
import { formatCalendarDate, formatNumber } from '@/lib/format'
import type { DailyMetrics } from './data'

const chartConfig = {
  visits: { label: 'Visits', color: 'var(--chart-1)' },
  total_hours: { label: 'Finalized person-hours', color: 'var(--chart-2)' },
} satisfies ChartConfig

export function DailyCharts({ daily }: { daily: DailyMetrics[] }) {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>
            <Typography variant="h3">Daily visits</Typography>
          </CardTitle>
          <CardDescription>
            All visits overlapping each date in the reporting timezone.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer
            config={chartConfig}
            className="h-64 w-full"
            role="img"
            aria-label="Daily visit counts. The exact values are also in the daily data table below."
          >
            <BarChart accessibilityLayer data={daily} margin={{ left: 0, right: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={formatCalendarDate}
                minTickGap={32}
                tickLine={false}
                axisLine={false}
              />
              <YAxis allowDecimals={false} width={42} tickLine={false} axisLine={false} />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(value) => formatCalendarDate(String(value))}
                  />
                }
              />
              <Bar
                dataKey="visits"
                fill="var(--color-visits)"
                radius={[3, 3, 0, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>
            <Typography variant="h3">Finalized person-hours</Typography>
          </CardTitle>
          <CardDescription>
            Closed visits without forgotten sign-outs. Time is clipped to each date.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer
            config={chartConfig}
            className="h-64 w-full"
            role="img"
            aria-label="Daily finalized person-hours. The exact values are also in the daily data table below."
          >
            <LineChart accessibilityLayer data={daily} margin={{ left: 0, right: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={formatCalendarDate}
                minTickGap={32}
                tickLine={false}
                axisLine={false}
              />
              <YAxis tickFormatter={formatNumber} width={42} tickLine={false} axisLine={false} />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(value) => formatCalendarDate(String(value))}
                  />
                }
              />
              <Line
                dataKey="total_hours"
                type="monotone"
                stroke="var(--color-total_hours)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ChartContainer>
        </CardContent>
      </Card>
    </div>
  )
}
