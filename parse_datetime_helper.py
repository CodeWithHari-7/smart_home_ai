df['Datetime'] = pd.to_datetime(
    df['Date'] + ' ' + df['Time']
)

df = df.sort_values('Datetime')