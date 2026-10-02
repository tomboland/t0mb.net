{-# LANGUAGE OverloadedStrings #-}
-- Full-review embedding and film-specific page wrappers.
module CinemaRendering (embedReviews, renderCinema, wrapCinema) where

import qualified Cinema as C
import qualified View as V
import Publishing (siteFields, bodySnapshot, TagIndex, tagLinks)
import Data.Aeson (Value)
import Control.Monad (forM)
import Data.List (isPrefixOf)
import Hakyll hiding (renderTags)
import Text.HTML.TagSoup (Tag(..), parseTags, renderTags)

-- Load only the rendered Markdown, without a standalone review's navigation.
embedReviews :: TagIndex -> Value -> Compiler Value
embedReviews tags view = do
  embedded <- forM (V.ls "reviews" view) $ \review -> do
    body <- loadSnapshotBody (fromFilePath $ V.str "source" review) bodySnapshot
    let prefix = "review-" ++ V.str "id" review ++ "-body-"
        url = V.str "url" review
        resolve link
          | null link || "/" `isPrefixOf` link = link
          | "#" `isPrefixOf` link = "#" ++ prefix ++ drop 1 link
          | ':' `elem` takeWhile (/='/') link = link
          | otherwise = url ++ link
        namespace (TagOpen name attrs) = TagOpen name
          [(key, if key `elem` ["id", "for"] then prefix ++ value
                 else if key `elem` ["aria-describedby", "aria-labelledby"] then unwords (map (prefix ++) $ words value)
                 else value) | (key,value) <- attrs]
        namespace tag = tag
        html = withUrls resolve $ renderTags $ map namespace $ parseTags body
    pure $ V.set [("htmlBody",V.val html),("image",C.reviewImage review),("postTags",tagLinks tags $ fromFilePath $ V.str "source" review)] review
  pure $ V.set [("embeddedReviews",V.values embedded)] view

renderCinema :: String -> Value -> Item String -> Compiler (Item String)
renderCinema template view item =
  loadAndApplyTemplate (fromFilePath $ "templates/cinema/"++template++".html") context item
    >>= wrapCinema view
  where context=V.viewContext view <> siteFields

wrapCinema :: Value -> Item String -> Compiler (Item String)
wrapCinema view item =
  loadAndApplyTemplate "templates/film-section.html" context item
    >>= loadAndApplyTemplate "templates/default.html" context >>= relativizeUrls
  where context=V.viewContext view <> siteFields

